"""Score a search run: rules over everything, LLM over the top slice.

Scoring every job with the LLM would mean dozens of calls per search against a
free-tier model, so the deterministic scorer runs first and decides which jobs are
worth spending calls on. Every job therefore always has a score, and a dead or
rate-limited provider only costs precision on the shortlist.
"""

import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from llm import client as llm

from ..models import Job
from . import llm_scorer
from .rules import score_job

logger = logging.getLogger(__name__)

SCORE_FIELDS = ["score", "score_reasons", "missing_skills", "scored_by", "scored_at"]


def score_run(search_run):
    profile = getattr(search_run.user, "profile", None)
    if profile is None:
        raise ValueError(f"user {search_run.user_id} has no profile; cannot score")

    jobs = list(
        Job.objects.filter(user=search_run.user, is_duplicate=False)
        .filter(Q(first_seen_run=search_run) | Q(score__isnull=True))
        .order_by("id")
    )
    if not jobs:
        return {"rule_scored": 0, "llm_scored": 0, "llm_error": None}

    now = timezone.now()
    for job in jobs:
        result = score_job(profile, job)
        _apply(job, result, now)
    Job.objects.bulk_update(jobs, SCORE_FIELDS)

    llm_scored, llm_error = _rescore_with_llm(profile, jobs)
    return {"rule_scored": len(jobs), "llm_scored": llm_scored, "llm_error": llm_error}


def _rescore_with_llm(profile, jobs):
    if not llm.is_configured():
        return 0, "OPENROUTER_API_KEY not set"

    shortlist = sorted(jobs, key=lambda job: job.score or 0, reverse=True)[
        : settings.LLM_SCORE_TOP_N
    ]
    if not shortlist:
        return 0, None

    batch_size = settings.LLM_SCORE_BATCH_SIZE
    updated = []
    first_error = None

    for start in range(0, len(shortlist), batch_size):
        batch = shortlist[start : start + batch_size]
        try:
            scores = llm_scorer.score_batch(profile, batch)
        except llm.LLMUnavailable as exc:
            # Provider down or rate limiting us: stop, do not hammer it.
            logger.warning("LLM scoring stopped after %s jobs: %s", len(updated), exc)
            first_error = first_error or str(exc)
            break
        except llm.LLMBadOutput as exc:
            # This batch is a loss; the next one may well be fine.
            logger.warning("LLM scoring skipped a batch: %s", exc)
            first_error = first_error or str(exc)
            continue

        now = timezone.now()
        by_id = {job.id: job for job in batch}
        for job_id, result in scores.items():
            job = by_id.get(job_id)
            if job is None:
                continue
            _apply(job, result, now)
            updated.append(job)

    if updated:
        Job.objects.bulk_update(updated, SCORE_FIELDS)
    return len(updated), first_error


def _apply(job, result, when):
    job.score = result.value
    job.score_reasons = result.reasons
    job.missing_skills = result.missing_skills
    job.scored_by = result.scored_by
    job.scored_at = when
