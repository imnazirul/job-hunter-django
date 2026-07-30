"""Deterministic 0-100 match score.

This runs on every job in every search. The LLM only re-scores the top slice, so
this is the primary scorer, not a fallback that never executes. It is built to be
pessimistic: a job with no identifiable skill overlap cannot climb out of the 30s
no matter how well the title and location line up.

Weights follow the brief: skills heaviest, then seniority, then location.
"""

from dataclasses import dataclass, field

from profiles.skill_vocabulary import canonical_skills, find_skills, guess_seniority

WEIGHT_SKILLS = 0.60
WEIGHT_SENIORITY = 0.25
WEIGHT_LOCATION = 0.15

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "principal"]
SENIORITY_GAP_SCORES = {0: 1.0, 1: 0.6, 2: 0.25}

# With nothing matched, the ceiling stays low however good the rest looks.
NO_SKILL_MATCH_CEILING = 35
ONE_SKILL_MATCH_CEILING = 55

MAX_MISSING_SKILLS_REPORTED = 8


@dataclass
class Score:
    value: int
    reasons: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    scored_by: str = "rules"


def score_job(profile, job):
    """profile needs skills/seniority/preferred_locations/remote_preference/excluded_keywords."""
    excluded = _excluded_hit(profile, job)
    if excluded:
        return Score(
            value=0,
            reasons=[f"excluded by your keyword {excluded!r}"],
            missing_skills=[],
        )

    reasons = []
    skills_component, matched, missing = _score_skills(profile, job, reasons)
    seniority_component = _score_seniority(profile, job, reasons)
    location_component = _score_location(profile, job, reasons)

    total = (
        skills_component * WEIGHT_SKILLS
        + seniority_component * WEIGHT_SENIORITY
        + location_component * WEIGHT_LOCATION
    )
    value = int(round(total * 100))

    if len(matched) == 0:
        value = min(value, NO_SKILL_MATCH_CEILING)
    elif len(matched) == 1:
        value = min(value, ONE_SKILL_MATCH_CEILING)

    return Score(
        value=max(0, min(100, value)),
        reasons=reasons,
        missing_skills=missing[:MAX_MISSING_SKILLS_REPORTED],
    )


def _job_text(job):
    return f"{job.title}\n{getattr(job, 'description', '') or ''}"


def _score_skills(profile, job, reasons):
    mine = {name.casefold(): name for name in canonical_skills(profile.skills)}
    wanted = find_skills(_job_text(job))

    if not mine:
        reasons.append("no skills on your profile yet, so skill fit could not be judged")
        return 0.25, [], []

    if not wanted:
        # Plenty of real postings list no recognisable tool at all.
        reasons.append("the posting names no skills we recognise, so skill fit is a guess")
        return 0.3, [], []

    matched = [name for name in wanted if name.casefold() in mine]
    missing = [name for name in wanted if name.casefold() not in mine]

    ratio = len(matched) / len(wanted)
    if matched:
        reasons.append(
            f"matches {len(matched)} of {len(wanted)} skills named in the posting: "
            + ", ".join(matched[:6])
        )
    else:
        reasons.append("none of the skills named in the posting are on your profile")
    if missing:
        reasons.append("missing: " + ", ".join(missing[:6]))

    return ratio, matched, missing


def _score_seniority(profile, job, reasons):
    mine = profile.seniority
    theirs = guess_seniority(job.title)

    if theirs == "unknown" or mine == "unknown":
        reasons.append("seniority not stated clearly on both sides")
        return 0.6

    gap = abs(SENIORITY_ORDER.index(mine) - SENIORITY_ORDER.index(theirs))
    component = SENIORITY_GAP_SCORES.get(gap, 0.0)
    if gap == 0:
        reasons.append(f"seniority matches ({mine})")
    elif SENIORITY_ORDER.index(theirs) > SENIORITY_ORDER.index(mine):
        reasons.append(f"posting is {theirs}, your profile says {mine}, a stretch")
    else:
        reasons.append(f"posting is {theirs}, your profile says {mine}, likely a step down")
    return component


def _score_location(profile, job, reasons):
    preference = profile.remote_preference
    job_remote = job.remote
    job_location = (job.location or "").casefold()
    wanted_locations = [place.casefold() for place in (profile.preferred_locations or []) if place]

    if job_remote and preference in ("remote", "any", "hybrid"):
        reasons.append("remote, which suits your preference")
        return 1.0
    if preference == "remote" and job_remote is False:
        reasons.append("on-site but you want remote")
        return 0.15

    if wanted_locations and job_location:
        for place in wanted_locations:
            if place in job_location or job_location in place:
                reasons.append(f"location matches {place}")
                return 1.0
        reasons.append(f"location {job.location!r} is not one of your preferred places")
        return 0.2

    if not wanted_locations:
        reasons.append("no location preference set, so location was not judged")
        return 0.5

    reasons.append("the posting does not say where the job is")
    return 0.4


def _excluded_hit(profile, job):
    haystack = _job_text(job).casefold()
    for keyword in profile.excluded_keywords or []:
        text = str(keyword).strip().casefold()
        if text and text in haystack:
            return keyword
    return None
