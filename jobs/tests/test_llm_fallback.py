"""The LLM misbehaving must never cost us a score or a search.

Each test drives the real scoring service with a fake OpenRouter reply and
asserts that jobs still come out scored, and that we do not burn more calls than
the brief allows.
"""

import json

import pytest

from jobs.models import Job, SearchRun
from jobs.normalize import fingerprint
from jobs.scoring import llm_scorer
from jobs.scoring.service import score_run
from llm import client as llm

DESCRIPTION = "We use Python, Django and PostgreSQL. Celery experience welcome."


def make_job(user, run, title="Senior Python Engineer", company="Acme", **extra):
    return Job.objects.create(
        user=user,
        source="remotive",
        source_job_id=extra.pop("source_job_id", title + company),
        title=title,
        company=company,
        location="Europe",
        remote=True,
        description=extra.pop("description", DESCRIPTION),
        url="https://example.com/job",
        fingerprint=fingerprint(company, title),
        first_seen_run=run,
        **extra,
    )


@pytest.fixture
def run(profile):
    return SearchRun.objects.create(user=profile.user, query={})


@pytest.fixture
def with_key(settings):
    settings.OPENROUTER_API_KEY = "test-key"
    return settings


def fake_chat(*replies):
    """Return a stand-in for llm.client._chat that yields the given replies."""
    calls = []

    def _chat(messages, **kwargs):
        calls.append(messages)
        index = min(len(calls) - 1, len(replies) - 1)
        return replies[index]

    _chat.calls = calls
    return _chat


@pytest.mark.django_db
def test_prose_instead_of_json_falls_back_to_rule_scores(run, profile, with_key, monkeypatch):
    chat = fake_chat("Sure! Here are the scores you asked for.")
    monkeypatch.setattr(llm, "_chat", chat)
    job = make_job(profile.user, run)

    result = score_run(run)

    assert result["rule_scored"] == 1
    assert result["llm_scored"] == 0
    assert result["llm_error"]

    job.refresh_from_db()
    assert job.score is not None
    assert job.scored_by == "rules"
    assert job.score_reasons
    # One retry and no more.
    assert len(chat.calls) == 2


@pytest.mark.django_db
def test_valid_json_on_the_retry_is_accepted(run, profile, with_key, monkeypatch):
    job = make_job(profile.user, run)
    good = json.dumps({"scores": [{"id": job.id, "score": 73, "reasons": ["solid overlap"]}]})
    chat = fake_chat("not json", good)
    monkeypatch.setattr(llm, "_chat", chat)

    result = score_run(run)

    assert result["llm_scored"] == 1
    job.refresh_from_db()
    assert job.score == 73
    assert job.scored_by == "llm"
    assert len(chat.calls) == 2


@pytest.mark.django_db
def test_json_wrapped_in_prose_and_fences_is_accepted(run, profile, with_key, monkeypatch):
    job = make_job(profile.user, run)
    reply = (
        "Here you go:\n```json\n"
        + json.dumps({"scores": [{"id": job.id, "score": 41, "reasons": ["thin overlap"]}]})
        + "\n```\nHope that helps!"
    )
    monkeypatch.setattr(llm, "_chat", fake_chat(reply))

    assert score_run(run)["llm_scored"] == 1
    job.refresh_from_db()
    assert job.score == 41


@pytest.mark.django_db
def test_hallucinated_job_ids_are_ignored(run, profile, with_key, monkeypatch):
    job = make_job(profile.user, run)
    reply = json.dumps({"scores": [{"id": job.id + 9999, "score": 99, "reasons": ["perfect"]}]})
    monkeypatch.setattr(llm, "_chat", fake_chat(reply))

    result = score_run(run)

    assert result["llm_scored"] == 0
    job.refresh_from_db()
    assert job.scored_by == "rules"


@pytest.mark.django_db
def test_out_of_range_scores_are_clamped(run, profile, with_key, monkeypatch):
    job = make_job(profile.user, run)
    reply = json.dumps({"scores": [{"id": job.id, "score": 480, "reasons": ["over the top"]}]})
    monkeypatch.setattr(llm, "_chat", fake_chat(reply))

    score_run(run)

    job.refresh_from_db()
    assert job.score == 100


@pytest.mark.django_db
def test_provider_down_stops_calling_and_keeps_rule_scores(run, profile, with_key, monkeypatch):
    calls = []

    def exploding_chat(messages, **kwargs):
        calls.append(messages)
        raise llm.LLMUnavailable("connection refused")

    monkeypatch.setattr(llm, "_chat", exploding_chat)
    for index in range(7):
        make_job(profile.user, run, title=f"Python Engineer {index}", source_job_id=f"job-{index}")

    result = score_run(run)

    assert result["rule_scored"] == 7
    assert result["llm_scored"] == 0
    assert "connection refused" in result["llm_error"]
    # Two batches were due; we stop after the first failure instead of hammering.
    assert len(calls) == 1
    assert all(job.scored_by == "rules" for job in Job.objects.all())


@pytest.mark.django_db
def test_no_api_key_means_rules_only_and_no_calls(run, profile, settings, monkeypatch):
    settings.OPENROUTER_API_KEY = ""

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the LLM must not be called without a key")

    monkeypatch.setattr(llm, "_chat", must_not_be_called)
    job = make_job(profile.user, run)

    result = score_run(run)

    assert result["rule_scored"] == 1
    assert result["llm_scored"] == 0
    job.refresh_from_db()
    assert job.scored_by == "rules"


@pytest.mark.django_db
def test_batches_never_exceed_five_jobs(run, profile, with_key, monkeypatch):
    batch_sizes = []

    def counting_chat(messages, **kwargs):
        prompt = messages[1]["content"]
        batch_sizes.append(prompt.count("\nid: ") + prompt.startswith("id: "))
        raise llm.LLMBadOutput("nope")

    monkeypatch.setattr(llm, "_chat", counting_chat)
    for index in range(12):
        make_job(profile.user, run, title=f"Python Engineer {index}", source_job_id=f"job-{index}")

    score_run(run)

    assert batch_sizes
    assert max(batch_sizes) <= 5


@pytest.mark.django_db
def test_score_batch_refuses_an_oversized_batch(run, profile, with_key):
    jobs = [
        make_job(profile.user, run, title=f"Engineer {index}", source_job_id=f"job-{index}")
        for index in range(6)
    ]
    with pytest.raises(ValueError):
        llm_scorer.score_batch(profile, jobs)


@pytest.mark.django_db
def test_empty_job_set_scores_nothing_without_error(run, profile, with_key, monkeypatch):
    monkeypatch.setattr(llm, "_chat", fake_chat("{}"))
    assert score_run(run) == {"rule_scored": 0, "llm_scored": 0, "llm_error": None}
