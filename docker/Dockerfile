# syntax=docker/dockerfile:1.7

# ---------- Stage 1: Flutter web build ----------
FROM ghcr.io/cirruslabs/flutter:stable AS frontend-builder
WORKDIR /frontend
COPY frontend/pubspec.yaml frontend/pubspec.lock ./
RUN flutter pub get
COPY frontend/ ./
# API_BASE_URL is empty => Flutter calls the same origin that serves the app.
# Override at build time with --build-arg API_BASE_URL=https://api.example.com if needed.
ARG API_BASE_URL=""
# --pwa-strategy=none disables Flutter's default service worker. Without it,
# `flutter_service_worker.js` aggressively caches `main.dart.js` in every
# visitor's browser and each new deploy needs two full reloads before it's
# picked up (and often gets stuck on stale bundles entirely). Turning the SW
# off makes every deploy visible on a single normal refresh — right behaviour
# for an actively iterated internal app.
RUN flutter build web --release --pwa-strategy=none \
    --dart-define=API_BASE_URL="${API_BASE_URL}"

# ---------- Stage 2: Backend (Python + uv) build ----------
FROM python:3.12-slim AS backend-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev || uv sync --no-dev

# ---------- Stage 3: Runtime ----------
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=backend-builder /app /app
COPY --from=frontend-builder /frontend/build/web /app/frontend_web
ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    PORT=80 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_WEB_DIR=/app/frontend_web
# Pre-download the local embedding model into fastembed's default cache
# (~/.cache/fastembed) so the container never blocks on a HuggingFace pull
# at startup. Bakes ~50 MB of ONNX weights into the image but yields sub-100ms
# cold-start embeds — critical for Azure Container Apps with no egress.
ARG EMBED_MODEL_NAME=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBED_MODEL_NAME}')"
# Bake the pre-seeded SQLite DB + media files into /data so container boot no
# longer runs the seeder. The `app.scripts.seed*` modules stay in the image
# and can be invoked manually for one-off regen (e.g. from an `az containerapp
# exec` shell), they're just not part of the boot command anymore.
COPY backend/data/flo.db   /data/flo.db
COPY backend/data/events   /data/events/
COPY backend/data/speakers /data/speakers/
COPY backend/data/reels    /data/reels/
EXPOSE 80
CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 80"]
