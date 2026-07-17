#!/usr/bin/env bash
# Start the FastAPI backend and Vite frontend dev server side-by-side.
#
# Usage:
#   ./dev.sh           — real binary (must run `make` first)
#   MOCK_BINARY=true ./dev.sh  — synthetic results, no binary needed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

export MOCK_BINARY="${MOCK_BINARY:-false}"
export COMPRESTIMATOR_PATH="${COMPRESTIMATOR_PATH:-$REPO_ROOT/ess_comprestimator}"
export DEV_CORS="true"   # allow the Vite dev server origin in the CORS allowlist

# ── Git hooks ─────────────────────────────────────────────────────────────────
# Copy hooks from scripts/hooks/ into .git/hooks/ if they are not already there
# or are older than the source. This keeps hooks in sync without a hook manager.
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"
if [[ -d "$HOOKS_SRC" ]]; then
  for hook in "$HOOKS_SRC"/*; do
    name="$(basename "$hook")"
    if [[ ! -f "$HOOKS_DST/$name" ]] || [[ "$hook" -nt "$HOOKS_DST/$name" ]]; then
      cp "$hook" "$HOOKS_DST/$name"
      chmod +x "$HOOKS_DST/$name"
      echo "▶ Installed git hook: $name"
    fi
  done
fi

# ── Python deps ───────────────────────────────────────────────────────────────
VENV="$REPO_ROOT/.venv"
if [[ ! -f "$VENV/bin/activate" ]]; then
  echo "▶ Creating Python virtual environment…"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_ROOT/backend/requirements.txt"

# ── Node deps ─────────────────────────────────────────────────────────────────
if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  echo "▶ Installing frontend dependencies…"
  (cd "$REPO_ROOT/frontend" && npm install)
fi

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
