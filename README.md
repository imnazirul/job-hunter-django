# JobHunter API

Django 5 + DRF + Celery. Standalone project: no npm, no dependency on the web or
desktop apps. All the logic lives here; the two clients are thin.

## Running with Docker

    cp .env.example .env
    docker compose up --build
    docker compose exec api python manage.py migrate
    docker compose exec api python manage.py createsuperuser

- API: http://localhost:8000
- OpenAPI schema: http://localhost:8000/api/schema/
- Swagger UI: http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/

## Running without Docker

Needs Python 3.13 plus a Postgres and Redis you point `.env` at.

    py -3.13 -m venv .venv
    .venv\Scripts\pip install -r requirements-dev.txt
    .venv\Scripts\python manage.py migrate
    .venv\Scripts\python manage.py runserver

## Tests

SQLite, Celery in eager mode, HTTP mocked. No infrastructure needed.

    .venv\Scripts\python -m pytest

Covered: source normalisation, fuzzy dedup, the LLM-returns-garbage fallback
chain, cross-user isolation, and the search flow end to end. Django's own ORM is
not retested.

## Endpoints

    POST   /api/auth/register/
    POST   /api/auth/token/           obtain access + refresh
    POST   /api/auth/token/refresh/
    GET    /api/auth/me/

    GET    /api/profile/              creates an empty profile on first read
    PATCH  /api/profile/              set reviewed=true to unlock searching
    GET    /api/cvs/
    POST   /api/cvs/                  multipart upload, queues parsing
    GET    /api/cvs/{id}/             poll for status and the parsed draft
    POST   /api/cvs/{id}/apply-draft/ copy a draft over the profile

    GET    /api/sources/              which boards exist and are configured
    POST   /api/searches/             starts a search, returns 202
    GET    /api/searches/{id}/        per-source progress for polling
    GET    /api/jobs/                 filters: q, min_score, source, remote,
                                      search_run, include_duplicates, ordering
    GET    /api/jobs/{id}/

## How a search runs

`POST /api/searches/` creates a SearchRun plus one SourceRun row per usable
source, then fires a Celery chord: one `fetch_source` task per board in parallel,
and a `finish_search` callback that dedupes and scores.

A board that times out, rate limits us or returns nonsense leaves its own
SourceRun marked failed and nothing else. The run still completes, marked
`partial`, and `/api/searches/{id}/` shows which board let us down.

## Scoring

Weights follow the brief: skill overlap 60%, seniority fit 25%, location and
remote fit 15%.

The deterministic scorer in `jobs/scoring/rules.py` runs over every job. Then the
top `LLM_SCORE_TOP_N` jobs are re-scored by the model in batches of at most
`LLM_SCORE_BATCH_SIZE` (hard capped at 5). This is a deliberate change from
"LLM-score everything": a search returning 300 jobs would otherwise cost 60 calls
against a free-tier model. Every job always has a score, and the LLM only
sharpens the shortlist.

Failure handling, in order: JSON is extracted from whatever the model wrapped it
in, validated, retried once on rejection, and then abandoned. A rate limit or a
dead provider stops the loop immediately rather than hammering it. Jobs whose
batch failed keep their rule score.

## Adding a job source

1. Write `jobs/sources/yourboard.py` with a `JobSource` subclass: set `key`,
   `name`, `requires_key`, implement `is_configured()` and `search(query)`,
   return `RawJob` objects, raise the `SourceError` subclasses from `base.py`.
2. Add it to `_SOURCES` in `jobs/sources/registry.py`.
3. Add a normalisation test with a captured sample payload.

Note the provider's rate limit and terms in the module docstring.

## Not built yet

Everything past slice 1: the other fourteen sources, the LinkedIn URL builder,
document generation, sending, follow-ups, the reply watcher, the scheduler,
tracker statuses and CSV/XLSX export.
