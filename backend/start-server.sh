#!/bin/sh

set -eu

APP_ENV_NORMALIZED="$(printf '%s' "${APP_ENV:-dev}" | tr '[:upper:]' '[:lower:]')"
APP_MODULE="${UVICORN_APP:-app.main:app}"
APP_DIR="${UVICORN_APP_DIR:-/app}"
HOST="${UVICORN_HOST:-0.0.0.0}"
PORT="${UVICORN_PORT:-8000}"
WORKERS="${UVICORN_WORKERS:-${WEB_CONCURRENCY:-}}"

if [ -z "$WORKERS" ]; then
  case "$APP_ENV_NORMALIZED" in
    prod|production)
      WORKERS="2"
      ;;
    *)
      WORKERS="1"
      ;;
  esac
fi

case "$WORKERS" in
  ''|*[!0-9]*)
    echo "UVICORN_WORKERS must be a positive integer." >&2
    exit 1
    ;;
esac

if [ "$WORKERS" -lt 1 ]; then
  echo "UVICORN_WORKERS must be >= 1." >&2
  exit 1
fi

echo "Starting RRviewer backend with ${WORKERS} worker(s) on ${HOST}:${PORT} (APP_ENV=${APP_ENV_NORMALIZED})"
exec uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" --app-dir "$APP_DIR" --workers "$WORKERS"