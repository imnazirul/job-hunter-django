"""Search orchestration.

One Celery task per source so they run in parallel and fail independently, then a
chord callback that dedupes and scores whatever arrived. A source that times out
leaves a failed SourceRun row and nothing else: the run still completes, marked
partial, and the UI can show which board let us down.
"""

import logging
from dataclasses import dataclass

from celery import chord, shared_task
from django.db.models.functions import Length
from django.utils import timezone

from .dedup import cluster_jobs
from .models import Job, SearchRun, SearchStatus, SourceRun, SourceStatus
from .normalize import fingerprint
from .scoring.service import score_run
from .sources.base import SearchQuery, SourceError, SourceNotConfigured, SourceRateLimited
from .sources.registry import get_source

logger = logging.getLogger(__name__)

JOBS_PER_SOURCE = 50


def build_query(profile):
    return SearchQuery(
        titles=tuple(profile.target_titles or []),
        keywords=tuple((profile.skills or [])[:5]),
        locations=tuple(profile.preferred_locations or []),
        remote_only=profile.remote_preference == "remote",
        limit=JOBS_PER_SOURCE,
    )


def dispatch(search_run):
    """Fan out one task per source, then dedupe and score in the callback."""
    source_keys = list(
        search_run.sources.filter(status=SourceStatus.PENDING).values_list("source_key", flat=True)
    )
    if not source_keys:
        raise ValueError(f"search run {search_run.pk} has no pending sources")

    header = [fetch_source.s(search_run.pk, key) for key in source_keys]
    return chord(header)(finish_search.s(search_run.pk))


@shared_task
def fetch_source(search_run_id, source_key):
    search_run = SearchRun.objects.select_related("user").get(pk=search_run_id)
    source_run = search_run.sources.get(source_key=source_key)

    SourceRun.objects.filter(pk=source_run.pk).update(
        status=SourceStatus.RUNNING, started_at=timezone.now()
    )
    SearchRun.objects.filter(pk=search_run_id, started_at__isnull=True).update(
        status=SearchStatus.RUNNING, started_at=timezone.now()
    )

    profile = search_run.user.profile
    query = build_query(profile)

    try:
        raw_jobs = get_source(source_key).search(query)
    except SourceNotConfigured as exc:
        return _finish_source(source_run, SourceStatus.SKIPPED, error=str(exc))
    except SourceRateLimited as exc:
        return _finish_source(source_run, SourceStatus.RATE_LIMITED, error=str(exc))
    except SourceError as exc:
        return _finish_source(source_run, SourceStatus.FAILED, error=str(exc))
    except Exception as exc:
        # Deliberate catch-all at the task boundary: the brief requires that one
        # broken board cannot fail the whole search. The traceback is logged in
        # full and the error text is stored on the row, so nothing is hidden.
        logger.exception("source %s raised an unexpected error", source_key)
        return _finish_source(source_run, SourceStatus.FAILED, error=f"{type(exc).__name__}: {exc}")

    fetched, created = _store_jobs(search_run, raw_jobs)
    return _finish_source(source_run, SourceStatus.OK, fetched=fetched, created=created)


def _finish_source(source_run, status, *, fetched=0, created=0, error=""):
    SourceRun.objects.filter(pk=source_run.pk).update(
        status=status,
        fetched=fetched,
        created=created,
        error=error[:2000],
        finished_at=timezone.now(),
    )
    return {
        "source": source_run.source_key,
        "status": status,
        "fetched": fetched,
        "created": created,
    }


def _store_jobs(search_run, raw_jobs):
    created_count = 0
    for raw in raw_jobs:
        fields = {
            "title": raw.title,
            "company": raw.company,
            "location": raw.location or "",
            "remote": raw.remote,
            "description": raw.description or "",
            "url": raw.url,
            "apply_url": raw.apply_url or "",
            "salary_text": raw.salary_text or "",
            "tags": raw.tags or [],
            "posted_at": raw.posted_at,
            "fingerprint": fingerprint(raw.company, raw.title),
        }
        # Re-running a search refreshes the posting but must not rewrite which
        # run first found it, hence create_defaults (Django 5.0+).
        _, created = Job.objects.update_or_create(
            user=search_run.user,
            source=raw.source,
            source_job_id=raw.source_job_id,
            defaults=fields,
            create_defaults={**fields, "first_seen_run": search_run},
        )
        created_count += int(created)
    return len(raw_jobs), created_count


@shared_task
def finish_search(source_results, search_run_id):
    search_run = SearchRun.objects.select_related("user").get(pk=search_run_id)

    duplicates = mark_duplicates(search_run.user)

    try:
        score_counts = score_run(search_run)
    except ValueError as exc:
        # No profile. Results are still worth keeping, so record and move on.
        logger.error("scoring skipped for run %s: %s", search_run_id, exc)
        score_counts = {"rule_scored": 0, "llm_scored": 0, "llm_error": str(exc)}

    results = [result for result in source_results if isinstance(result, dict)]
    ok_sources = [result for result in results if result.get("status") == SourceStatus.OK]
    total_fetched = sum(result.get("fetched", 0) for result in results)
    total_created = sum(result.get("created", 0) for result in results)

    if not ok_sources:
        status = SearchStatus.FAILED
    elif len(ok_sources) < len(results):
        status = SearchStatus.PARTIAL
    else:
        status = SearchStatus.COMPLETED

    SearchRun.objects.filter(pk=search_run_id).update(
        status=status,
        jobs_found=total_fetched,
        jobs_new=total_created,
        duplicates_marked=duplicates,
        finished_at=timezone.now(),
    )
    return {
        "search_run": search_run_id,
        "status": status,
        "jobs_found": total_fetched,
        "jobs_new": total_created,
        "duplicates": duplicates,
        **score_counts,
    }


@dataclass
class _JobRef:
    id: int
    source: str
    title: str
    company: str
    description_length: int


def mark_duplicates(user):
    """Recompute duplicate flags across everything this user has stored.

    Recomputing rather than only looking at new rows matters because a posting
    from a company's own Greenhouse board should take over as canonical from an
    aggregator copy found last week.
    """
    rows = (
        Job.objects.filter(user=user)
        .annotate(description_length=Length("description"))
        .values("id", "source", "title", "company", "description_length")
    )
    refs = [_JobRef(**row) for row in rows]
    if not refs:
        return 0

    canonical_ids = set()
    duplicates_by_canonical = {}
    for cluster in cluster_jobs(refs):
        canonical_ids.add(cluster.canonical.id)
        if cluster.duplicates:
            duplicates_by_canonical[cluster.canonical.id] = [job.id for job in cluster.duplicates]

    Job.objects.filter(id__in=canonical_ids).update(is_duplicate=False, duplicate_of=None)
    total = 0
    for canonical_id, duplicate_ids in duplicates_by_canonical.items():
        Job.objects.filter(id__in=duplicate_ids).update(
            is_duplicate=True, duplicate_of=canonical_id
        )
        total += len(duplicate_ids)
    return total
