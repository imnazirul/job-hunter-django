from datetime import timedelta
from pathlib import Path

from .env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = env_bool("DJANGO_DEBUG", False)

# A weak default is only tolerable because it is refused outside DEBUG.
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-dev-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "accounts",
    "profiles",
    "jobs",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "jobhunter.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "jobhunter.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "jobhunter"),
        "USER": env_str("POSTGRES_USER", "jobhunter"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", "jobhunter"),
        "HOST": env_str("POSTGRES_HOST", "localhost"),
        "PORT": env_str("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env_str("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "JobHunter API",
    "DESCRIPTION": "Job search, scoring and application automation.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Three models have a "status" field, and without these the generated client
    # ends up with names like Status14cEnum.
    "ENUM_NAME_OVERRIDES": {
        "CVStatusEnum": "profiles.models.CVStatus.choices",
        "SearchStatusEnum": "jobs.models.SearchStatus.choices",
        "SourceStatusEnum": "jobs.models.SourceStatus.choices",
    },
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["http://localhost:3000"])

REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 600)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 540)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

OPENROUTER_API_KEY = env_str("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = env_str("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")
OPENROUTER_BASE_URL = env_str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_TIMEOUT = env_int("OPENROUTER_TIMEOUT", 60)
OPENROUTER_APP_URL = env_str("OPENROUTER_APP_URL", "http://localhost:3000")
OPENROUTER_APP_NAME = env_str("OPENROUTER_APP_NAME", "JobHunter")

LLM_CV_TEXT_LIMIT = env_int("LLM_CV_TEXT_LIMIT", 6000)
LLM_JOB_DESC_LIMIT = env_int("LLM_JOB_DESC_LIMIT", 1200)
LLM_SCORE_BATCH_SIZE = min(env_int("LLM_SCORE_BATCH_SIZE", 5), 5)
LLM_SCORE_TOP_N = env_int("LLM_SCORE_TOP_N", 40)

MAX_CV_UPLOAD_BYTES = env_int("MAX_CV_UPLOAD_BYTES", 10 * 1024 * 1024)

JOB_SOURCE_KEYS = {
    "adzuna_app_id": env_str("ADZUNA_APP_ID", ""),
    "adzuna_app_key": env_str("ADZUNA_APP_KEY", ""),
    "jooble_api_key": env_str("JOOBLE_API_KEY", ""),
    "usajobs_api_key": env_str("USAJOBS_API_KEY", ""),
    "usajobs_email": env_str("USAJOBS_EMAIL", ""),
    "rapidapi_key": env_str("RAPIDAPI_KEY", ""),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
