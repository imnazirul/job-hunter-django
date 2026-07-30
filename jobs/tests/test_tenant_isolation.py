"""One user must never see another user's data.

Every list endpoint filters on request.user and every detail endpoint scopes its
queryset, so a wrong id is a 404 rather than someone else's job. These tests exist
to keep it that way when the queryset code gets edited later.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from jobs.models import Job, SearchRun
from jobs.normalize import fingerprint
from profiles.models import CVDocument


@pytest.fixture
def alice_job(user):
    return Job.objects.create(
        user=user,
        source="remotive",
        source_job_id="alice-1",
        title="Senior Python Engineer",
        company="Acme",
        url="https://example.com/alice-1",
        description="Python and Django",
        fingerprint=fingerprint("Acme", "Senior Python Engineer"),
        score=88,
    )


@pytest.fixture
def alice_run(user):
    return SearchRun.objects.create(user=user, query={"titles": ["Senior Python Engineer"]})


@pytest.fixture
def alice_cv(user):
    return CVDocument.objects.create(
        user=user,
        file=SimpleUploadedFile("alice.pdf", b"%PDF-1.4 fake"),
        original_filename="alice.pdf",
        size_bytes=12,
        draft={"skills": ["Python"], "full_name": "Alice Example"},
        status="parsed",
    )


@pytest.mark.django_db
def test_job_list_only_returns_own_jobs(alice_client, bob_client, alice_job):
    mine = alice_client.get("/api/jobs/")
    assert mine.status_code == 200
    assert [job["id"] for job in mine.data["results"]] == [alice_job.id]

    theirs = bob_client.get("/api/jobs/")
    assert theirs.status_code == 200
    assert theirs.data["results"] == []


@pytest.mark.django_db
def test_job_detail_of_another_user_is_404(bob_client, alice_job):
    assert bob_client.get(f"/api/jobs/{alice_job.id}/").status_code == 404


@pytest.mark.django_db
def test_search_run_detail_of_another_user_is_404(bob_client, alice_run):
    assert bob_client.get(f"/api/searches/{alice_run.id}/").status_code == 404


@pytest.mark.django_db
def test_search_run_list_is_scoped(alice_client, bob_client, alice_run):
    assert len(alice_client.get("/api/searches/").data["results"]) == 1
    assert bob_client.get("/api/searches/").data["results"] == []


@pytest.mark.django_db
def test_cv_detail_of_another_user_is_404(bob_client, alice_cv):
    assert bob_client.get(f"/api/cvs/{alice_cv.id}/").status_code == 404


@pytest.mark.django_db
def test_cannot_apply_another_users_cv_draft(bob_client, alice_cv):
    response = bob_client.post(f"/api/cvs/{alice_cv.id}/apply-draft/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_profile_endpoint_returns_the_callers_own_profile(alice_client, bob_client, profile):
    mine = alice_client.get("/api/profile/")
    assert mine.status_code == 200
    assert mine.data["full_name"] == "Alice Example"

    theirs = bob_client.get("/api/profile/")
    assert theirs.status_code == 200
    assert theirs.data["full_name"] == ""
    assert theirs.data["id"] != mine.data["id"]


@pytest.mark.django_db
def test_patching_the_profile_cannot_touch_another_user(bob_client, profile):
    bob_client.patch("/api/profile/", {"full_name": "Bob Impostor"}, format="json")
    profile.refresh_from_db()
    assert profile.full_name == "Alice Example"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ["/api/jobs/", "/api/searches/", "/api/profile/", "/api/cvs/", "/api/sources/"],
)
def test_anonymous_access_is_rejected(api_client, path):
    assert api_client.get(path).status_code == 401


@pytest.mark.django_db
def test_search_requires_a_reviewed_profile(alice_client, profile):
    profile.reviewed = False
    profile.save(update_fields=["reviewed"])

    response = alice_client.post("/api/searches/")
    assert response.status_code == 409


@pytest.mark.django_db
def test_search_without_a_profile_at_all_is_a_conflict(alice_client):
    response = alice_client.post("/api/searches/")
    assert response.status_code == 409
