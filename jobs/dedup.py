"""Fuzzy duplicate detection across job sources.

The same opening reaches us as "Senior Python Engineer" from Remotive, "Senior
Python Engineer (m/f/d)" from an Arbeitnow feed and "Senior Python Engineer -
Berlin" from an aggregator. Normalising the company first and fuzzy-matching the
title second catches those without merging genuinely different roles at the same
employer, which a company-only match would do.

Works on anything with .title, .company, .source and .description, so it can be
unit tested without touching the database.
"""

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .normalize import normalize_company, normalize_title

# Higher wins when two postings collide. A company's own board is the most
# accurate and most likely to still be open; aggregators lag and mangle titles.
SOURCE_PRIORITY = {
    "greenhouse": 30,
    "lever": 30,
    "ashby": 30,
    "remotive": 20,
    "remoteok": 20,
    "arbeitnow": 20,
    "himalayas": 20,
    "themuse": 20,
    "usajobs": 20,
    "adzuna": 10,
    "jooble": 10,
    "jsearch": 10,
}
DEFAULT_PRIORITY = 15

TITLE_MATCH_THRESHOLD = 88


@dataclass
class Cluster:
    canonical: object
    duplicates: list = field(default_factory=list)


def cluster_jobs(jobs):
    """Group jobs into clusters, best posting first in each."""
    groups = {}
    singletons = []

    for index, job in enumerate(jobs):
        company_key = normalize_company(getattr(job, "company", ""))
        if not company_key:
            # No company name means nothing reliable to compare against.
            singletons.append(job)
            continue
        groups.setdefault(company_key, []).append((index, job))

    clusters = []
    for _, entries in sorted(groups.items()):
        clusters.extend(_cluster_within_company(entries))
    clusters.extend(Cluster(canonical=job) for job in singletons)
    return clusters


def _cluster_within_company(entries):
    ranked = sorted(entries, key=lambda entry: _rank_key(entry[1], entry[0]))

    clusters = []
    titles = []
    for _, job in ranked:
        title = normalize_title(getattr(job, "title", ""))
        matched = None
        for existing_title, cluster in zip(titles, clusters):
            if _titles_match(title, existing_title):
                matched = cluster
                break
        if matched is None:
            clusters.append(Cluster(canonical=job))
            titles.append(title)
        else:
            matched.duplicates.append(job)
    return clusters


def _titles_match(left, right):
    if not left or not right:
        return False
    if left == right:
        return True
    return fuzz.token_set_ratio(left, right) >= TITLE_MATCH_THRESHOLD


def _rank_key(job, index):
    priority = SOURCE_PRIORITY.get(getattr(job, "source", ""), DEFAULT_PRIORITY)
    # Negatives so that higher priority and longer descriptions sort first.
    return (-priority, -_description_length(job), index)


def _description_length(job):
    """Callers that cannot afford to load every description pass the length instead."""
    if hasattr(job, "description_length"):
        return job.description_length or 0
    return len(getattr(job, "description", "") or "")
