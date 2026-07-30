"""The contract every job board module implements.

A source does one thing: take a SearchQuery and return RawJob objects, or raise a
SourceError explaining why it could not. It never writes to the database and
never decides what to do about failure. That keeps each new board a single small
file with nothing to know about the rest of the system.
"""

from dataclasses import dataclass, field
from datetime import datetime

import requests

USER_AGENT = "JobHunter/0.1 (personal job search tool)"
DEFAULT_TIMEOUT = 20


class SourceError(Exception):
    """Base class for expected, per-source failures."""


class SourceUnavailable(SourceError):
    """Network failure, timeout, or a provider-side error."""


class SourceRateLimited(SourceError):
    """The provider told us to slow down."""


class SourceNotConfigured(SourceError):
    """A required API key is missing."""


@dataclass(frozen=True)
class SearchQuery:
    titles: tuple = ()
    keywords: tuple = ()
    locations: tuple = ()
    remote_only: bool = False
    limit: int = 50

    @property
    def primary_title(self):
        return self.titles[0] if self.titles else ""


@dataclass
class RawJob:
    source: str
    source_job_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    remote: bool = None
    posted_at: datetime = None
    salary_text: str = ""
    apply_url: str = ""
    tags: list = field(default_factory=list)


class JobSource:
    key = ""
    name = ""
    # True when the module cannot work without an API key from settings.
    requires_key = False

    def is_configured(self):
        return True

    def search(self, query):
        raise NotImplementedError


def fetch_json(url, *, params=None, headers=None, method="GET", json_body=None, timeout=None):
    """HTTP with the failure modes mapped onto SourceError.

    Lives in base because "one dead API must not fail the whole search" depends
    on every source raising the same three exceptions for the same three
    situations. Sources that need something else can still use requests directly.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=request_headers,
            timeout=timeout or DEFAULT_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise SourceUnavailable(f"timed out after {timeout or DEFAULT_TIMEOUT}s: {url}") from exc
    except requests.RequestException as exc:
        raise SourceUnavailable(f"request failed: {exc}") from exc

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise SourceRateLimited(f"rate limited, Retry-After={retry_after}")
    if response.status_code in (401, 403):
        raise SourceNotConfigured(
            f"provider rejected our credentials ({response.status_code}): {response.text[:200]}"
        )
    if response.status_code >= 400:
        raise SourceUnavailable(f"HTTP {response.status_code}: {response.text[:200]}")

    try:
        return response.json()
    except ValueError as exc:
        raise SourceUnavailable(f"response was not JSON: {response.text[:200]}") from exc
