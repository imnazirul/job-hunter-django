"""LLM re-scoring, in batches of at most five jobs.

Everything here assumes the model is weak: descriptions are truncated hard, the
requested JSON is flat, ids are echoed back so a shuffled reply can still be
matched up, and any job the model skips or mangles simply keeps its rule score.
A batch that comes back unusable costs that batch's jobs nothing.
"""

import logging

from django.conf import settings

from llm import client as llm
from llm.coerce import as_int, as_text_list, require_list, require_mapping

from .rules import Score

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You rate how well a candidate fits a job. You are strict: most jobs are a "
    "poor fit and should score below 50. You reply with one JSON object and "
    "nothing else."
)

USER_TEMPLATE = """Candidate:
seniority: {seniority}
years of experience: {years}
skills: {skills}
wants: {titles}
locations: {locations} (remote preference: {remote})

Score each job below from 0 to 100 for this candidate.
Weighting, most important first: overlap between the candidate's skills and the
job's requirements, then seniority fit, then location and remote fit.
Be strict. 80+ means an excellent fit with almost every requirement met. 50 means
plausible but clearly imperfect. Below 30 means do not bother applying.

Reply with exactly this JSON:
{{"scores": [{{"id": <the job id>, "score": <0-100>, "reasons": ["short reason", ...],
 "missing_skills": ["skill the job wants that the candidate lacks", ...]}}]}}

Include one entry for every job id listed. No markdown, no commentary.

Jobs:
{jobs}"""


def score_batch(profile, jobs):
    """Return {job.id: Score} for whichever jobs the model scored usably.

    Raises llm.LLMUnavailable if the provider is unreachable, and
    llm.LLMBadOutput if two attempts both produced nothing usable.
    """
    if not jobs:
        return {}
    if len(jobs) > settings.LLM_SCORE_BATCH_SIZE:
        raise ValueError(
            f"batch of {len(jobs)} exceeds LLM_SCORE_BATCH_SIZE={settings.LLM_SCORE_BATCH_SIZE}"
        )

    wanted_ids = {job.id for job in jobs}
    prompt = USER_TEMPLATE.format(
        seniority=profile.seniority,
        years=profile.years_experience if profile.years_experience is not None else "not stated",
        skills=", ".join(profile.skills[:25]) or "not stated",
        titles=", ".join(profile.target_titles[:6]) or "not stated",
        locations=", ".join(profile.preferred_locations[:6]) or "anywhere",
        remote=profile.remote_preference,
        jobs=_render_jobs(jobs),
    )

    def validate(payload):
        return _validate_scores(payload, wanted_ids)

    return llm.complete_json(SYSTEM_PROMPT, prompt, validate, max_tokens=1200)


def _render_jobs(jobs):
    limit = settings.LLM_JOB_DESC_LIMIT
    blocks = []
    for job in jobs:
        description = (job.description or "").strip()[:limit]
        blocks.append(
            f"id: {job.id}\n"
            f"title: {job.title}\n"
            f"company: {job.company}\n"
            f"location: {job.location or 'not stated'}"
            f"{' (remote)' if job.remote else ''}\n"
            f"description: {description or 'not provided'}\n"
        )
    return "\n---\n".join(blocks)


def _validate_scores(payload, wanted_ids):
    data = require_mapping(payload, "score response")
    entries = require_list(data.get("scores"), "scores")

    results = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        job_id = as_int(entry.get("id"))
        if job_id not in wanted_ids:
            # A hallucinated id is not worth guessing about.
            continue
        value = as_int(entry.get("score"), minimum=0, maximum=100)
        if value is None:
            continue
        results[job_id] = Score(
            value=value,
            reasons=as_text_list(entry.get("reasons"), max_items=5, max_length=200),
            missing_skills=as_text_list(entry.get("missing_skills"), max_items=8),
            scored_by="llm",
        )

    if not results:
        raise llm.LLMBadOutput(
            f"no usable scores in reply; wanted ids {sorted(wanted_ids)}, got {entries!r:.200}"
        )
    return results
