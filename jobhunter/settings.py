from datetime import timedelta
from pathlib import Path

from .env import env_bool, env_db_url, env_int, env_list, env_str, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Must precede every env_* call below. A no-op in production: the platform
# injects the real variables and no .env is shipped in the image.
load_dotenv(BASE_DIR / ".env")

DEBUG = env_bool("DJANGO_DEBUG", False)

# A weak default is only tolerable because it is refused outside DEBUG.
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-dev-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

# Railway assigns the domain after the service exists, so it cannot be in a
# checked-in env file. Trust the one it injects rather than making every deploy
# hand-copy it into DJANGO_ALLOWED_HOSTS.
PUBLIC_DOMAIN = env_str("RAILWAY_PUBLIC_DOMAIN", "")
if PUBLIC_DOMAIN and PUBLIC_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PUBLIC_DOMAIN)

# The admin login POST is cross-origin as far as Django is concerned once a
# proxy terminates TLS, so the scheme has to be spelled out here.
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])
if PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f"https://{PUBLIC_DOMAIN}")

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
    # Serves the admin and DRF assets straight from gunicorn; there is no nginx
    # in front of us on a managed host.
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
    "default": env_db_url("DATABASE_URL")
    or {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "jobhunter"),
        "USER": env_str("POSTGRES_USER", "jobhunter"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", "jobhunter"),
        "HOST": env_str("POSTGRES_HOST", "localhost"),
        "PORT": env_str("POSTGRES_PORT", "5432"),
    }
}
# Reconnecting per request is wasteful when the database is a network hop away.
DATABASES["default"]["CONN_MAX_AGE"] = env_int("DB_CONN_MAX_AGE", 60)

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
MEDIA_ROOT = env_str("MEDIA_ROOT", str(BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# TLS ends at the platform's edge, so Django only learns the original scheme
# from this header. Without it every redirect and absolute URL comes out http.
if env_bool("DJANGO_BEHIND_PROXY", not DEBUG):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
# Off by default: HSTS is remembered by browsers and is painful to walk back.
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

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
HAS_REDIS = bool(env_str("REDIS_URL", ""))
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 600)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 540)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Only the Remotive source uses the cache, to stay under its rate limit. A
# missing Redis should cost us that, not 500 every request that touches it.
if HAS_REDIS:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

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
