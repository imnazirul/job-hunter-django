"""End to end: POST a search, get scored jobs out, with Remotive faked.

Celery runs eagerly under the test settings, so this also proves the chord wiring
holds together.
"""

import pytest
import responses

from jobs.models import Job, SearchRun, SearchStatus, SourceStatus
from jobs.sources.remotive import API_URL

POSTING = {
    "id": 900,
    "url": "https://remotive.com/remote-jobs/900",
    "title": "Senior Python Engineer",
    "company_name": "Acme Inc.",
    "tags": ["python", "django"],
    "job_type": "full_time",
    "publication_date": "2026-07-20T10:00:00",
    "candidate_required_location": "Europe",
    "salary": "",
    "description": "<p>Python, Django, PostgreSQL and Celery.</p>",
}

DUPLICATE_POSTING = {
    **POSTING,
    "id": 901,
    "title": "Senior Python Engineer (m/f/d)",
    "company_name": "ACME",
    "description": "<p>Python and Django.</p>",
}


@pytest.mark.django_db
@responses.activate
def test_search_stores_scores_and_marks_duplicates(alice_client, profile):
    responses.add(
        responses.GET, API_URL, json={"jobs": [POSTING, DUPLICATE_POSTING]}, status=200
    )

    response = alice_client.post("/api/searches/")
    assert response.status_code == 202

    run = SearchRun.objects.get(pk=response.data["id"])
    assert run.status == SearchStatus.COMPLETED
    assert run.sources.get(source_key="remotive").status == SourceStatus.OK
    assert run.jobs_new == 2
    assert run.duplicates_marked == 1

    listing = alice_client.get("/api/jobs/")
    assert len(listing.data["results"]) == 1
    job = listing.data["results"][0]
    assert job["score"] is not None
    assert job["scored_by"] == "rules"

    detail = alice_client.get(f"/api/jobs/{job['id']}/")
    assert detail.data["score_reasons"]
    assert detail.data["duplicate_count"] == 1
    assert "<p>" not in detail.data["description"]


@pytest.mark.django_db
@responses.activate
def test_dead_source_leaves_the_run_failed_but_recorded(alice_client, profile):
    responses.add(responses.GET, API_URL, body="gateway timeout", status=504)

    response = alice_client.post("/api/searches/")
    assert response.status_code == 202

    run = SearchRun.objects.get(pk=response.data["id"])
    assert run.status == SearchStatus.FAILED
    source_run = run.sources.get(source_key="remotive")
    assert source_run.status == SourceStatus.FAILED
    assert "504" in source_run.error
    assert Job.objects.count() == 0

    # The failure is visible through the API, which is what the UI polls.
    detail = alice_client.get(f"/api/searches/{run.pk}/")
    assert detail.data["sources"][0]["status"] == SourceStatus.FAILED


@pytest.mark.django_db
@responses.activate
def test_rerunning_a_search_updates_rather_than_duplicates(alice_client, profile):
    responses.add(responses.GET, API_URL, json={"jobs": [POSTING]}, status=200)

    first = alice_client.post("/api/searches/")
    second = alice_client.post("/api/searches/")

    assert first.status_code == 202
    assert second.status_code == 202
    assert Job.objects.count() == 1

    job = Job.objects.get()
    assert job.first_seen_run_id == first.data["id"]


@pytest.mark.django_db
@responses.activate
def test_empty_result_set_completes_with_no_jobs(alice_client, profile):
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    response = alice_client.post("/api/searches/")
    run = SearchRun.objects.get(pk=response.data["id"])

    assert run.status == SearchStatus.COMPLETED
    assert run.jobs_found == 0
    assert alice_client.get("/api/jobs/").data["results"] == []
