"""The list of job sources, written out by hand.

Explicit imports beat autodiscovery here: adding a board is one line, and a typo
fails at import time instead of silently searching one fewer site.
"""

from .remotive import RemotiveSource

_SOURCES = [
    RemotiveSource(),
]

SOURCES = {source.key: source for source in _SOURCES}


def all_sources():
    return list(SOURCES.values())


def get_source(key):
    try:
        return SOURCES[key]
    except KeyError:
        raise KeyError(f"unknown job source {key!r}; known: {sorted(SOURCES)}") from None


def usable_sources():
    """Sources with whatever credentials they need. Unusable ones get skipped."""
    return [source for source in all_sources() if source.is_configured()]
