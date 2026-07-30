"""Tiny env readers so settings stay readable and fail loudly on typos.

Deliberately not django-environ: we need four functions, not a dependency.
"""

import os


class MissingSetting(Exception):
    pass


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
