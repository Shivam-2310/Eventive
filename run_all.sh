#!/usr/bin/env bash
# run_all.sh — start Flo backend (FastAPI, :8000) and frontend (Flutter web,
# :3000) together. Every run:
#   1. Frees whatever is already bound to the target ports.
#   2. Writes stdout+stderr for each service to a fresh timestamped log file
#      under ./logs/. Previous logs are never overwritten.
#   3. Maintains ./logs/backend.latest.log and ./logs/frontend.latest.log
#      symlinks pointing at the current run for `tail -f` convenience.
#
# Target: WSL Ubuntu / native Linux / macOS with bash >= 4.
# Prereqs on $PATH: uv, flutter, curl. Optional: lsof (preferred) or fuser.
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
API_BASE_URL="${API_BASE_URL:-http://localhost:${BACKEND_PORT}}"

# Pick a Flutter web device that actually works in the current environment.
# In WSL, `flutter run -d chrome` reliably fails to launch the Windows Chrome
# binary (`chrome.exe --user-data-dir=/tmp/...` blows up on cross-fs perms), so
# we transparently fall back to the headless `web-server` device — the user
# then opens http://localhost:3000 in their Windows browser. Callers can force
# a specific device via FLUTTER_DEVICE=chrome (or =web-server) if they know
# their setup works.
if [[ -z "${FLUTTER_DEVICE:-}" ]]; then
  if grep -qi microsoft /proc/version 2>/dev/null; then
    FLUTTER_DEVICE="web-server"
  else
    FLUTTER_DEVICE="chrome"
  fi
fi

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="${REPO_ROOT}/backend"
FRONTEND_DIR="${REPO_ROOT}/frontend"
LOG_DIR="${REPO_ROOT}/logs"

RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
BACKEND_LOG="${LOG_DIR}/backend_${RUN_STAMP}.log"
FRONTEND_LOG="${LOG_DIR}/frontend_${RUN_STAMP}.log"
mkdir -p "${LOG_DIR}"

C_INFO='\033[1;36m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_OFF='\033[0m'
log()  { printf "${C_INFO}[flo]${C_OFF} %s\n" "$*"; }
warn() { printf "${C_WARN}[flo]${C_OFF} %s\n" "$*"; }
err()  { printf "${C_ERR}[flo]${C_OFF} %s\n" "$*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command not found on PATH: $1"
    exit 1
  fi
}

kill_port() {
  local port="$1" pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"${port}" 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "${port}" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)"
  else
    warn "Neither lsof nor fuser is installed; cannot free port ${port} automatically."
    return 0
  fi
  if [[ -n "${pids}" ]]; then
    log "Killing PID(s) on port ${port}: $(echo "${pids}" | tr '\n' ' ')"
    echo "${pids}" | xargs -r kill -9 2>/dev/null || true
    sleep 1
  else
    log "Port ${port} is free."
  fi
}

# Update logs/<svc>.latest.log to point at this run. Prefer symlink; fall back
# to a copy on filesystems that reject symlinks (some Windows-mounted WSL paths).
update_latest_pointer() {
  local svc="$1" target_basename="$2"
  local pointer="${LOG_DIR}/${svc}.latest.log"
  rm -f "${pointer}" 2>/dev/null || true
  if ! ln -s "${target_basename}" "${pointer}" 2>/dev/null; then
    cp -f "${LOG_DIR}/${target_basename}" "${pointer}" 2>/dev/null || true
  fi
}

require_cmd uv
require_cmd flutter
require_cmd curl

log "Freeing ports ${BACKEND_PORT} (backend) and ${FRONTEND_PORT} (frontend)..."
kill_port "${BACKEND_PORT}"
kill_port "${FRONTEND_PORT}"

# Create the log files up front so `tail -f` from another terminal works
# immediately, even before the services have produced any output.
: > "${BACKEND_LOG}"
: > "${FRONTEND_LOG}"
update_latest_pointer "backend"  "backend_${RUN_STAMP}.log"
update_latest_pointer "frontend" "frontend_${RUN_STAMP}.log"
log "Log directory: ${LOG_DIR}"
log "  Backend  log: ${BACKEND_LOG}"
log "  Frontend log: ${FRONTEND_LOG}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  local ec=$?
  echo
  log "Shutting down..."
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill -TERM "${FRONTEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill -TERM "${BACKEND_PID}" 2>/dev/null || true
  fi
  sleep 1
  kill_port "${BACKEND_PORT}" || true
  kill_port "${FRONTEND_PORT}" || true
  exit "${ec}"
}
trap cleanup EXIT INT TERM

log "Starting backend on port ${BACKEND_PORT}..."
(
  cd "${BACKEND_DIR}"
  if [[ ! -f .env && -f .env.example ]]; then
    printf '[flo] backend/.env missing; copying from .env.example\n'
    cp .env.example .env
  fi
  uv sync
  uv run alembic upgrade head
  uv run python -m app.scripts.seed || printf '[flo] Seed step reported an error (may already be seeded).\n'
  exec uv run python -m uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT}" --reload
) >> "${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
log "Backend PID: ${BACKEND_PID}   (tail -f ${LOG_DIR}/backend.latest.log)"

log "Waiting for backend /healthz to respond..."
for _ in $(seq 1 60); do
  if curl -fs "http://localhost:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
    log "Backend is healthy."
    break
  fi
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    err "Backend exited before becoming healthy. Full log: ${BACKEND_LOG}"
    exit 1
  fi
  sleep 1
done

if ! curl -fs "http://localhost:${BACKEND_PORT}/healthz" >/dev/null 2>&1; then
  err "Backend did not become healthy within 60s. Full log: ${BACKEND_LOG}"
  exit 1
fi

log "Starting Flutter web on port ${FRONTEND_PORT} (device=${FLUTTER_DEVICE}, API_BASE_URL=${API_BASE_URL})..."
(
  cd "${FRONTEND_DIR}"
  flutter pub get
  exec flutter run -d "${FLUTTER_DEVICE}" \
    --web-port "${FRONTEND_PORT}" \
    --web-hostname 0.0.0.0 \
    --dart-define=API_BASE_URL="${API_BASE_URL}"
) >> "${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!
log "Frontend PID: ${FRONTEND_PID}  (tail -f ${LOG_DIR}/frontend.latest.log)"

log "----------------------------------------------------------"
log "  Backend :  http://localhost:${BACKEND_PORT}  (docs: /docs)"
log "  Frontend:  http://localhost:${FRONTEND_PORT}"
if [[ "${FLUTTER_DEVICE}" == "web-server" ]]; then
  log "  (device=web-server) Open http://localhost:${FRONTEND_PORT} manually in your browser."
fi
log "  Logs    :  ${LOG_DIR}/"
log "               tail -f ${LOG_DIR}/backend.latest.log"
log "               tail -f ${LOG_DIR}/frontend.latest.log"
log "  Press Ctrl+C to stop both."
log "----------------------------------------------------------"

# Wait until the BACKEND exits (or Ctrl+C). The frontend dying is treated as
# non-fatal — a flaky Chrome-in-WSL launch or a Flutter rebuild loop should NOT
# tear down the backend, otherwise `curl` smoke tests + Postman collections
# lose their target the second Chrome misbehaves.
frontend_reported_dead=0
while kill -0 "${BACKEND_PID}" 2>/dev/null; do
  if [[ "${frontend_reported_dead}" -eq 0 ]] && ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    warn "Frontend exited. Backend stays up so you can still hit http://localhost:${BACKEND_PORT}."
    warn "  See ${FRONTEND_LOG}"
    warn "  Restart the frontend with: (cd frontend && flutter run -d ${FLUTTER_DEVICE} --web-port ${FRONTEND_PORT})"
    frontend_reported_dead=1
  fi
  sleep 1
done

err "Backend exited. See ${BACKEND_LOG}"
