#!/usr/bin/env bash
# Start the FastAPI backend and Vite frontend dev server side-by-side.
#
# Usage:
#   ./dev.sh           — real binary (must run `make` first)
#   MOCK_BINARY=true ./dev.sh  — synthetic results, no binary needed
#
# Requires:
#   - Python 3.9+  with backend/requirements.txt installed
#   - Node 18+     with frontend/node_modules installed  (npm install in frontend/)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

export MOCK_BINARY="${MOCK_BINARY:-false}"
export COMPRESTIMATOR_PATH="${COMPRESTIMATOR_PATH:-$REPO_ROOT/comprestimator}"
export DEV_CORS="true"   # allow the Vite dev server origin in the CORS allowlist

echo "▶ Starting backend on :$BACKEND_PORT  (MOCK_BINARY=$MOCK_BINARY)"
python3 -m uvicorn backend.main:app \
  --reload \
  --port "$BACKEND_PORT" \
  --app-dir "$REPO_ROOT" &
BACKEND_PID=$!

echo "▶ Starting frontend on :$FRONTEND_PORT"
(cd "$REPO_ROOT/frontend" && npm run dev -- --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

# Graceful shutdown on Ctrl-C
trap 'echo ""; echo "Stopping…"; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; wait' SIGINT SIGTERM

echo ""
echo "  Backend  → http://localhost:$BACKEND_PORT/api/docs"
echo "  Frontend → http://localhost:$FRONTEND_PORT"
echo ""
echo "Press Ctrl-C to stop."
wait
