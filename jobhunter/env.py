"""Tiny env readers so settings stay readable and fail loudly on typos.

Deliberately not django-environ: we need four functions, not a dependency.
"""

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class MissingSetting(Exception):
    pass


def load_dotenv(path):
    """Populate os.environ from a KEY=VALUE file, if one is there.

    docker-compose reads .env itself and managed hosts inject real variables, so
    this exists for `manage.py` run straight from a shell. A name already in the
    environment is a deliberate override and always wins.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


_MISSING = object()


def env_str(name, default=_MISSING):
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _MISSING:
            raise MissingSetting(f"{name} is required but not set")
        return default
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise MissingSetting(f"{name} must be an integer, got {value!r}") from exc


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None or value == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_db_url(name):
    """Parse a postgres:// URL into Django's DATABASES["default"] shape, or None.

    Managed hosts (Railway, Heroku, Fly) hand out one URL rather than the five
    POSTGRES_* pieces, so accept both instead of making every deploy translate.
    """
    value = os.environ.get(name)
    if value is None or value == "":
        return None

    parts = urlsplit(value)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise MissingSetting(f"{name} must be a postgres:// URL, got {parts.scheme or value!r}")

    config = {
        "ENGINE": "django.db.backends.postgresql",
        # Everything in a URL is percent-encoded; passwords routinely need it.
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
    }
    sslmode = parse_qs(parts.query).get("sslmode", [""])[0]
    if sslmode:
        config["OPTIONS"] = {"sslmode": sslmode}
    return config
