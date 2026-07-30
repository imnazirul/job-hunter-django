import pytest
import responses

from jobs.sources.base import SearchQuery, SourceUnavailable
from jobs.sources.remotive import API_URL, RemotiveSource

SAMPLE_JOB = {
    "id": 1234,
    "url": "https://remotive.com/remote-jobs/software-dev/senior-python-1234",
    "title": "Senior Python Engineer",
    "company_name": "Acme Inc.",
    "category": "Software Development",
    "tags": ["python", "django"],
    "job_type": "full_time",
    "publication_date": "2026-07-01T09:30:00",
    "candidate_required_location": "Europe",
    "salary": "70000 - 90000 EUR",
    "description": "<p>We need <b>Python</b> and Django.</p><ul><li>Celery</li></ul>",
}


def query():
    return SearchQuery(titles=("Senior Python Engineer",), limit=50)


@responses.activate
def test_normalizes_a_full_posting():
    responses.add(responses.GET, API_URL, json={"jobs": [SAMPLE_JOB]}, status=200)

    jobs = RemotiveSource().search(query())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remotive"
    assert job.source_job_id == "1234"
    assert job.title == "Senior Python Engineer"
    assert job.company == "Acme Inc."
    assert job.remote is True
    assert job.location == "Europe"
    assert job.salary_text == "70000 - 90000 EUR"
    assert "full_time" in job.tags
    assert job.description == "We need Python and Django.\n\n- Celery"
    assert job.posted_at is not None
    assert job.posted_at.tzinfo is not None


@responses.activate
def test_postings_missing_required_fields_are_dropped():
    incomplete = [
        {**SAMPLE_JOB, "id": 1, "title": ""},
        {**SAMPLE_JOB, "id": 2, "company_name": ""},
        {**SAMPLE_JOB, "id": 3, "url": ""},
        {**SAMPLE_JOB, "id": None},
        "not even an object",
    ]
    responses.add(responses.GET, API_URL, json={"jobs": incomplete}, status=200)

    assert RemotiveSource().search(query()) == []


@responses.activate
def test_empty_result_set_is_not_an_error():
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)
    assert RemotiveSource().search(query()) == []


@responses.activate
def test_missing_jobs_key_is_not_an_error():
    responses.add(responses.GET, API_URL, json={"job-count": 0}, status=200)
    assert RemotiveSource().search(query()) == []


@responses.activate
def test_bad_publication_date_does_not_lose_the_job():
    responses.add(
        responses.GET,
        API_URL,
        json={"jobs": [{**SAMPLE_JOB, "publication_date": "last tuesday"}]},
        status=200,
    )
    jobs = RemotiveSource().search(query())
    assert len(jobs) == 1
    assert jobs[0].posted_at is None


@responses.activate
def test_server_error_raises_source_unavailable():
    responses.add(responses.GET, API_URL, body="upstream on fire", status=502)
    with pytest.raises(SourceUnavailable):
        RemotiveSource().search(query())


@responses.activate
def test_non_json_body_raises_source_unavailable():
    responses.add(responses.GET, API_URL, body="<html>maintenance</html>", status=200)
    with pytest.raises(SourceUnavailable):
        RemotiveSource().search(query())


@responses.activate
def test_duplicate_ids_across_terms_are_collapsed():
    responses.add(responses.GET, API_URL, json={"jobs": [SAMPLE_JOB, SAMPLE_JOB]}, status=200)
    assert len(RemotiveSource().search(query())) == 1


@responses.activate
def test_second_call_is_served_from_cache():
    responses.add(responses.GET, API_URL, json={"jobs": [SAMPLE_JOB]}, status=200)

    source = RemotiveSource()
    source.search(query())
    source.search(query())

    assert len(responses.calls) == 1
