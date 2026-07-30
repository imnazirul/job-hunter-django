import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from profiles.models import CandidateProfile

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.com", password="pw-alice-12345")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bob@example.com", password="pw-bob-12345")


@pytest.fixture
def profile(user):
    return CandidateProfile.objects.create(
        user=user,
        full_name="Alice Example",
        seniority="senior",
        years_experience=8,
        skills=["Python", "Django", "PostgreSQL", "Celery", "Docker"],
        target_titles=["Senior Python Engineer"],
        preferred_locations=["Berlin"],
        remote_preference="remote",
        reviewed=True,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def alice_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def bob_client(other_user):
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client
