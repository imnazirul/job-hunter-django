"""Test settings: no Postgres, no Redis, no network.

Keeps the real settings module free of test branching. The unit tests we care
about (normalization, dedup, LLM fallback, tenant isolation) do not exercise
anything Postgres-specific, so SQLite is an honest stand-in for them.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret")
os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR  # noqa: E402

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test"}
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

MEDIA_ROOT = BASE_DIR / "test-media"

# Absent on purpose: every LLM path must survive an unconfigured key.
OPENROUTER_API_KEY = ""

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
