# Flo Companion Backend

FastAPI + SQLite (WAL + `sqlite-vec`) backend for the Flo event-companion hackathon build.

All development is done **inside WSL Ubuntu 22.04** (production is Linux, `sqlite-vec` is
Linux-only, and Alembic/SQLite/ffmpeg behave identically to the container).

## Quickstart (WSL bash)

```bash
# one-time
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL
uv python install 3.12

# every-day
cd /mnt/c/Users/shivamnagpal/Downloads/lightning-mcqueenz/backend
uv sync
cp .env.example .env      # edit values as needed
uv run alembic upgrade head
uv run python -m app.scripts.seed
uv run python -m uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000/docs` in your Windows browser.

## Docker (mirrors prod)

```bash
docker build -f docker/Dockerfile -t flo-backend .
docker run --rm -p 8080:80 --env-file backend/.env flo-backend
curl localhost:8080/healthz
```

## Layout

```
backend/
  app/
    main.py            # FastAPI factory
    api/               # HTTP + WS routers
    domain/            # services (only layer that touches SQLAlchemy)
    infra/             # config, db, ws_manager, scheduler, blob, security
    models/            # SQLAlchemy ORM
    schemas/           # Pydantic DTOs
    scripts/           # seed, reset_admin
    workers/           # background jobs (embeddings, transcode, matching)
  alembic/             # migrations
  seed/                # events.csv, interests.json, reels/*.mp4
  tests/
```

Every layer talks only to the one below it: `api → domain → models`. The API layer
never touches SQLAlchemy directly — always through a `domain/*_service.py`.

## Environment variables

See [.env.example](.env.example) for the full list. The interesting ones:

| Var | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/flo.db` | SQLite path |
| `DATA_DIR` | `./data` | where reels + uploads land |
| `LLM_PROVIDER` | `stub` | `stub` (deterministic fake) or `gemini` |
| `GEMINI_API_KEY` | *(empty)* | required only when `LLM_PROVIDER=gemini` |
| `CORS_ORIGINS` | `*` | comma-separated, wide-open in dev |

## Auth

Phases 0–13 leave every endpoint open and pass `user_id` explicitly so `/docs` stays
one-click testable. Phase 14 lands JWT auth + admin gate + rate limits + `sqlglot`
NL2SQL guard all at once.
