import pytest

from llm.client import LLMBadOutput
from profiles.parsing import _validate_draft, draft_from_keywords, parse_profile
from profiles.skill_vocabulary import canonical_skills, find_skills, guess_seniority

CV = """Alice Example
alice@example.com | +49 30 1234567
Berlin, Germany

Senior Backend Engineer with 8 years of experience building web services.

EXPERIENCE
Senior Backend Engineer, Acme Inc. 2020-2026
- Built Django and Django REST Framework services on PostgreSQL
- Ran background work with Celery and Redis
- Deployed with Docker and Kubernetes on AWS

SKILLS
Python, Django, PostgreSQL, Celery, Docker, Kubernetes, AWS, pytest
"""


class TestKeywordFallback:
    def test_finds_the_obvious_facts(self):
        draft = draft_from_keywords(CV)
        assert draft["full_name"] == "Alice Example"
        assert draft["contact_email"] == "alice@example.com"
        assert draft["years_experience"] == 8
        assert draft["seniority"] == "senior"
        assert "Python" in draft["skills"]
        assert "PostgreSQL" in draft["skills"]

    def test_finds_a_phone_number(self):
        assert draft_from_keywords(CV)["phone"]

    def test_suggests_target_titles(self):
        titles = draft_from_keywords(CV)["target_titles"]
        assert any("engineer" in title.lower() for title in titles)

    def test_survives_a_cv_with_nothing_recognisable(self):
        draft = draft_from_keywords("lorem ipsum dolor sit amet " * 20)
        assert draft["skills"] == []
        assert draft["seniority"] == "unknown"
        assert draft["years_experience"] is None


class TestValidateDraft:
    def test_coerces_sloppy_types(self):
        draft = _validate_draft(
            {
                "full_name": "Alice Example",
                "email": "alice@example.com",
                "years_experience": "8 years",
                "skills": "Python, Django , Python",
                "seniority": "SENIOR",
                "remote_preference": "Remote",
                "target_titles": ["Backend Engineer"],
            }
        )
        assert draft["years_experience"] == 8
        assert draft["skills"] == ["Python", "Django"]
        assert draft["seniority"] == "senior"
        assert draft["remote_preference"] == "remote"

    def test_unknown_enum_values_fall_back_to_defaults(self):
        draft = _validate_draft({"seniority": "ninja", "remote_preference": "moon base"})
        assert draft["seniority"] == "unknown"
        assert draft["remote_preference"] == "any"

    def test_nulls_become_empty_values(self):
        draft = _validate_draft({"full_name": None, "skills": None, "years_experience": None})
        assert draft["full_name"] == ""
        assert draft["skills"] == []
        assert draft["years_experience"] is None

    def test_absurd_years_are_clamped(self):
        assert _validate_draft({"years_experience": 400})["years_experience"] == 60

    def test_a_list_instead_of_an_object_is_rejected(self):
        with pytest.raises(LLMBadOutput):
            _validate_draft([{"full_name": "Alice"}])

    def test_a_string_instead_of_an_object_is_rejected(self):
        with pytest.raises(LLMBadOutput):
            _validate_draft("Alice is a senior engineer")


def test_parse_profile_without_a_key_uses_keywords(settings):
    settings.OPENROUTER_API_KEY = ""
    draft, parsed_with = parse_profile(CV)
    assert parsed_with == "keywords"
    assert "Python" in draft["skills"]


def test_parse_profile_falls_back_when_the_llm_is_broken(settings, monkeypatch):
    settings.OPENROUTER_API_KEY = "k"
    monkeypatch.setattr("llm.client._chat", lambda *args, **kwargs: "I cannot do that")

    draft, parsed_with = parse_profile(CV)

    assert parsed_with == "keywords"
    assert draft["contact_email"] == "alice@example.com"


def test_parse_profile_fills_gaps_the_model_left(settings, monkeypatch):
    settings.OPENROUTER_API_KEY = "k"
    monkeypatch.setattr(
        "llm.client._chat",
        lambda *args, **kwargs: '{"full_name": "Alice Example", "skills": []}',
    )

    draft, parsed_with = parse_profile(CV)

    assert parsed_with == "llm"
    assert "Python" in draft["skills"]
    assert draft["contact_email"] == "alice@example.com"
    assert draft["seniority"] == "senior"


def test_parse_profile_rejects_empty_text():
    with pytest.raises(ValueError):
        parse_profile("   ")


class TestVocabulary:
    def test_aliases_map_to_canonical_names(self):
        assert canonical_skills(["postgres"]) == ["PostgreSQL"]
        assert canonical_skills(["nodejs"]) == ["Node.js"]

    def test_unknown_skills_are_kept_as_written(self):
        assert canonical_skills(["Widget Wrangling"]) == ["Widget Wrangling"]

    def test_duplicates_collapse(self):
        assert canonical_skills(["Postgres", "PostgreSQL", "psql"]) == ["PostgreSQL"]

    def test_bare_go_is_not_matched(self):
        assert "Go" not in find_skills("I go to the office every day")

    def test_golang_is_matched(self):
        assert "Go" in find_skills("Backend work in Golang")

    def test_csharp_punctuation_matches(self):
        assert "C#" in find_skills("Built services in C#")

    def test_leadership_is_not_read_as_lead(self):
        assert guess_seniority("Demonstrated leadership on many projects") == "unknown"

    def test_senior_is_detected(self):
        assert guess_seniority("Senior Software Engineer") == "senior"
