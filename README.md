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

## Deploying to Railway

The Dockerfile is the production image: it installs runtime deps only, bakes
`collectstatic` in, runs `migrate` on boot and serves through gunicorn on
`$PORT`. `railway.json` points the healthcheck at `/healthz/`.

Set the service root directory to `backend-django` if the repo root is deployed.

Variables the API service needs:

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | 50 random characters. `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` — the reference, not a pasted URL, so it stays on the internal network |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `CORS_ALLOWED_ORIGINS` | the frontend's origin, e.g. `https://jobhunter.vercel.app` |
| `OPENROUTER_API_KEY` | required for LLM scoring; the rule scorer still runs without it |
| `OPENROUTER_APP_URL` | the frontend's origin, for OpenRouter attribution |
| job source keys | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `JOOBLE_API_KEY`, … — each empty one skips that board |

`DJANGO_DEBUG` stays unset. `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
pick up `RAILWAY_PUBLIC_DOMAIN` on their own; set them only for a custom domain.

Searches need a second service off the same repo with the start command
overridden to `celery -A jobhunter worker --loglevel=info`, sharing the API's
variables. Without it a search stays queued forever.

Two things this setup does not solve:

- **Uploaded CVs live on the container's disk.** Redeploys wipe them, and the
  worker is a separate container that cannot see what the API wrote, so CV
  parsing fails there. Both services need a shared Railway volume mounted at
  the same path with `MEDIA_ROOT` pointing to it — or object storage.
- **Without a Redis service** the cache silently falls back to per-process
  memory and Celery has no broker. The API serves fine; searches do not run.

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
