#!/usr/bin/env bash
# Run the API and the web interface together. Ctrl-C stops both.
set -euo pipefail

cd "$(dirname "$0")"

trap 'kill 0' EXIT

(cd backend && uv run --locked --no-sync uvicorn app.main:app --port 8000) &
(cd frontend && pnpm dev) &

wait
