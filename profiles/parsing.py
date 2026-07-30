"""Turn CV text into a profile draft the user can correct.

Two paths, and the caller does not need to care which ran: the LLM, or a keyword
scan when the LLM is unconfigured, unreachable or talking nonsense. The keyword
path is crude on purpose. It exists so the upload flow always reaches the review
screen, where a human fixes whatever it got wrong.
"""

import logging
import re

from django.conf import settings

from llm import client as llm
from llm.coerce import as_choice, as_int, as_text, as_text_list, require_mapping

from .skill_vocabulary import find_skills, guess_seniority

logger = logging.getLogger(__name__)

SENIORITY_CHOICES = ["intern", "junior", "mid", "senior", "lead", "principal", "unknown"]
REMOTE_CHOICES = ["remote", "hybrid", "onsite", "any"]

MAX_SKILLS = 40
MAX_TITLES = 8
MAX_LOCATIONS = 8

SYSTEM_PROMPT = (
    "You extract structured facts from CVs. You reply with one JSON object and "
    "nothing else. You never invent facts that are not in the CV."
)

USER_TEMPLATE = """Extract this person's profile from the CV text below.

Reply with exactly this JSON shape:
{{"full_name": string or null,
 "email": string or null,
 "phone": string or null,
 "location": string or null,
 "seniority": one of "intern","junior","mid","senior","lead","principal","unknown",
 "years_experience": integer or null,
 "skills": array of short strings,
 "target_titles": array of job titles this person should apply for,
 "preferred_locations": array of place names or country names,
 "remote_preference": one of "remote","hybrid","onsite","any",
 "summary": string, at most 400 characters}}

Rules:
- Use only what the CV states. If something is absent use null or an empty array.
- Do not guess years_experience from graduation dates. Only use it if stated or
  clearly computable from listed job dates.
- skills: concrete tools, languages and disciplines. No soft-skill filler.
- target_titles: titles matching what they have actually done, most recent first.
- remote_preference: "any" unless the CV says otherwise.
- No markdown, no commentary, JSON only.

CV text:
---
{cv_text}
---"""


def parse_profile(cv_text):
    """Return (draft dict, "llm" or "keywords")."""
    if not cv_text or not cv_text.strip():
        raise ValueError("cv_text is empty; extraction should have caught this")

    truncated = cv_text[: settings.LLM_CV_TEXT_LIMIT]

    if llm.is_configured():
        try:
            draft = llm.complete_json(
                SYSTEM_PROMPT,
                USER_TEMPLATE.format(cv_text=truncated),
                _validate_draft,
                max_tokens=900,
            )
            return _fill_gaps(draft, cv_text), "llm"
        except llm.LLMError as exc:
            logger.warning("CV parse fell back to keywords: %s", exc)
    else:
        logger.info("OPENROUTER_API_KEY not set, using keyword CV parse")

    return draft_from_keywords(cv_text), "keywords"


def _validate_draft(payload):
    data = require_mapping(payload, "CV profile")
    return {
        "full_name": as_text(data.get("full_name"), max_length=200),
        "contact_email": _first_email(as_text(data.get("email"), max_length=254)),
        "phone": as_text(data.get("phone"), max_length=50),
        "location": as_text(data.get("location"), max_length=200),
        "seniority": as_choice(data.get("seniority"), SENIORITY_CHOICES, "unknown"),
        "years_experience": as_int(data.get("years_experience"), minimum=0, maximum=60),
        "skills": as_text_list(data.get("skills"), max_items=MAX_SKILLS),
        "target_titles": as_text_list(data.get("target_titles"), max_items=MAX_TITLES),
        "preferred_locations": as_text_list(
            data.get("preferred_locations"), max_items=MAX_LOCATIONS
        ),
        "remote_preference": as_choice(data.get("remote_preference"), REMOTE_CHOICES, "any"),
        "summary": as_text(data.get("summary"), max_length=400),
    }


def _fill_gaps(draft, cv_text):
    """Patch the fields a weak model most often drops, from the raw CV text."""
    if not draft["skills"]:
        draft["skills"] = find_skills(cv_text, limit=MAX_SKILLS)
    if draft["seniority"] == "unknown":
        draft["seniority"] = guess_seniority(cv_text[:1500])
    if not draft["contact_email"]:
        draft["contact_email"] = _first_email(cv_text)
    return draft


def draft_from_keywords(cv_text):
    """A deliberately dumb profile draft. The user is expected to fix it."""
    head = cv_text[:1500]
    return {
        "full_name": _guess_name(cv_text),
        "contact_email": _first_email(cv_text),
        "phone": _first_phone(cv_text),
        "location": "",
        "seniority": guess_seniority(head),
        "years_experience": _guess_years(cv_text),
        "skills": find_skills(cv_text, limit=MAX_SKILLS),
        "target_titles": _guess_titles(head),
        "preferred_locations": [],
        "remote_preference": "any",
        "summary": "",
    }


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\d)")
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b[^.\n]{0,30}experience", re.IGNORECASE)

TITLE_WORDS = (
    "engineer",
    "developer",
    "designer",
    "manager",
    "analyst",
    "scientist",
    "architect",
    "consultant",
    "administrator",
    "specialist",
    "technician",
    "nurse",
    "teacher",
    "accountant",
    "marketer",
    "recruiter",
    "writer",
)


def _first_email(text):
    match = EMAIL_RE.search(text or "")
    return match.group(0).strip(".") if match else ""


def _first_phone(text):
    for line in (text or "").splitlines()[:40]:
        match = PHONE_RE.search(line)
        if match:
            candidate = match.group(0).strip()
            digits = sum(char.isdigit() for char in candidate)
            if 7 <= digits <= 15:
                return candidate[:50]
    return ""


def _guess_years(text):
    match = YEARS_RE.search(text or "")
    if not match:
        return None
    years = int(match.group(1))
    return years if 0 < years <= 60 else None


def _guess_name(text):
    """The first short line with no digits or @ is usually the name on a CV."""
    for line in (text or "").splitlines()[:6]:
        candidate = line.strip()
        if not candidate or "@" in candidate or any(char.isdigit() for char in candidate):
            continue
        words = candidate.split()
        if 1 < len(words) <= 4 and len(candidate) <= 60:
            return candidate[:200]
    return ""


def _guess_titles(head):
    titles = []
    for line in head.splitlines():
        candidate = line.strip(" -|,")
        if not 3 < len(candidate) <= 60:
            continue
        lowered = candidate.lower()
        if any(word in lowered for word in TITLE_WORDS):
            if candidate not in titles:
                titles.append(candidate)
        if len(titles) >= 3:
            break
    return titles
