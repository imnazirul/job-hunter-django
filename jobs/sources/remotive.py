"""Remotive public job API. No key required.

Endpoint: GET https://remotive.com/api/remote-jobs?search=<term>&limit=<n>
Every listing is remote by definition.

Remotive's response carries a legal notice asking that the data be attributed and
not scraped aggressively. I have not verified a specific documented
requests-per-hour figure, so this module is deliberately conservative: at most
three requests per search, one second apart, and responses cached for 30 minutes.
Check their terms before raising any of that.
"""

import hashlib
import logging
import time
from datetime import datetime, timezone

from django.core.cache import cache

from ..normalize import strip_html
from .base import JobSource, RawJob, SourceUnavailable, fetch_json

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"
CACHE_TTL_SECONDS = 30 * 60
MAX_TERMS_PER_SEARCH = 3
PAUSE_BETWEEN_REQUESTS = 1.0


class RemotiveSource(JobSource):
    key = "remotive"
    name = "Remotive"
    requires_key = False

    def search(self, query):
        terms = [term for term in query.titles[:MAX_TERMS_PER_SEARCH] if term.strip()]
        if not terms:
            terms = [""]

        per_term_limit = max(10, query.limit // len(terms))
        jobs = {}
        failures = []

        for index, term in enumerate(terms):
            if index:
                time.sleep(PAUSE_BETWEEN_REQUESTS)
            try:
                payload = self._fetch(term, per_term_limit)
            except SourceUnavailable as exc:
                # One bad term should not lose the results from the other two.
                failures.append(f"{term!r}: {exc}")
                continue
            for item in payload.get("jobs") or []:
                raw = self._to_raw_job(item)
                if raw is not None:
                    jobs[raw.source_job_id] = raw

        if not jobs and failures:
            raise SourceUnavailable("; ".join(failures))
        if failures:
            logger.warning("remotive: some terms failed: %s", "; ".join(failures))

        return list(jobs.values())[: query.limit]

    def _fetch(self, term, limit):
        # Hashed because search terms contain spaces and colons, which are not
        # safe in cache keys across every backend.
        digest = hashlib.sha1(f"{term.casefold()}:{limit}".encode("utf-8")).hexdigest()[:16]
        cache_key = f"remotive:{digest}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        params = {"limit": limit}
        if term:
            params["search"] = term
        payload = fetch_json(API_URL, params=params)
        if not isinstance(payload, dict):
            raise SourceUnavailable(f"expected a JSON object, got {type(payload).__name__}")

        cache.set(cache_key, payload, CACHE_TTL_SECONDS)
        return payload

    def _to_raw_job(self, item):
        if not isinstance(item, dict):
            return None
        source_job_id = str(item.get("id") or "").strip()
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        url = (item.get("url") or "").strip()
        # A posting without these is unusable downstream, so drop it here rather
        # than storing a row that can never be scored or applied to.
        if not (source_job_id and title and company and url):
            return None

        tags = [str(tag) for tag in (item.get("tags") or []) if tag]
        if item.get("job_type"):
            tags.append(str(item["job_type"]))

        return RawJob(
            source=self.key,
            source_job_id=source_job_id,
            title=title[:300],
            company=company[:200],
            url=url[:1000],
            description=strip_html(item.get("description") or ""),
            location=(item.get("candidate_required_location") or "")[:200],
            remote=True,
            posted_at=_parse_timestamp(item.get("publication_date")),
            salary_text=(item.get("salary") or "")[:200],
            tags=tags[:20],
        )


def _parse_timestamp(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.debug("remotive: unparseable publication_date %r", value)
        return None
    if parsed.tzinfo is None:
        # Remotive timestamps are UTC without an offset.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
