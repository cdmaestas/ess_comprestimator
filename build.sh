#!/usr/bin/env bash
# build.sh — end-to-end packaging pipeline
#
# Outputs (host-dependent):
#   macOS  →  dist-electron/Comprestimator-1.0.0.dmg  (arm64 + x64)
#   Linux  →  dist-electron/Comprestimator-1.0.0.AppImage  (x64, arm64)
#             dist-electron/comprestimator_1.0.0_amd64.deb
#             dist-electron/comprestimator-1.0.0.x86_64.rpm
#
# Prerequisites:
#   macOS : brew install node python3 gcc
#   Linux : apt install nodejs npm python3 python3-venv gcc
#           (or equivalent for your distro)
#   Both  : (cd frontend && npm install)
#           (cd electron  && npm install)
#
# Python dependencies are installed automatically into .venv/ during step 3.
#
# Usage:
#   ./build.sh                      — full build for current OS
#   ./build.sh --skip-frontend      — reuse existing frontend/dist/
#   ./build.sh --skip-pyinstaller   — reuse existing dist/comprestimator-backend

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ── Flags ─────────────────────────────────────────────────────────────────────
SKIP_FRONTEND=false
SKIP_PYINSTALLER=false
for arg in "$@"; do
  case "$arg" in
    --skip-frontend)    SKIP_FRONTEND=true ;;
    --skip-pyinstaller) SKIP_PYINSTALLER=true ;;
  esac
done

# ── Platform detection ────────────────────────────────────────────────────────
HOST_OS="$(uname -s)"   # Darwin | Linux
case "$HOST_OS" in
  Darwin) PLATFORM="mac"   ;;
  Linux)  PLATFORM="linux" ;;
  *)
    echo "ERROR: Unsupported host OS: $HOST_OS"
    echo "  Build on macOS for .dmg, or on Linux for .AppImage / .deb / .rpm."
    exit 1 ;;
esac
echo "Platform: $HOST_OS → building $PLATFORM package"

# ── Step 1: Build the Go binary ───────────────────────────────────────────────
echo "==> [1/5]  Build ess_comprestimator Go binary"
if ! command -v go &>/dev/null; then
  echo "ERROR: Go compiler not found on PATH"
  echo "       Install Go: brew install go"
  exit 1
fi

# Remove existing binary to avoid "already exists and is not an object file" error
rm -f ess_comprestimator

if ! go build -o ess_comprestimator .; then
  echo "ERROR: go build failed"
  exit 1
fi

echo "    Built: $ROOT/ess_comprestimator"

# ── Step 2: Build the React frontend ─────────────────────────────────────────
if [[ "$SKIP_FRONTEND" == "true" ]]; then
  echo "==> [2/5]  Skipping frontend build (--skip-frontend)"
else
  echo "==> [2/5]  Build React frontend"
  (cd frontend && npm install --prefer-offline 2>/dev/null || npm install)
  (cd frontend && npm run build)
fi

if [[ ! -d frontend/dist ]]; then
  echo "ERROR: frontend/dist does not exist. Run without --skip-frontend first."
  exit 1
fi

# ── Step 3: Bundle Python backend with PyInstaller ────────────────────────────
if [[ "$SKIP_PYINSTALLER" == "true" ]]; then
  echo "==> [3/5]  Skipping PyInstaller (--skip-pyinstaller)"
else
  echo "==> [3/5]  Bundle Python backend (PyInstaller)"

  # PEP 668 prevents pip from installing into the system Python on modern macOS
  # and most Linux distros.  Use a local venv instead — created once, reused on
  # subsequent builds.
  VENV="$ROOT/.venv"
  if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "    Creating Python virtual environment in .venv/"
    python3 -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"

  pip install --quiet --upgrade pip
  pip install --quiet -r backend/requirements.txt
  pip install --quiet pyinstaller

  python3 -m PyInstaller backend.spec --noconfirm --clean
  deactivate
fi

BACKEND_BIN="$ROOT/dist/comprestimator-backend"
if [[ ! -f "$BACKEND_BIN" ]]; then
  echo "ERROR: PyInstaller output not found at $BACKEND_BIN"
  exit 1
fi
echo "    Binary: $BACKEND_BIN  ($(du -sh "$BACKEND_BIN" | cut -f1))"

# ── Step 4: Install Electron dependencies ─────────────────────────────────────
echo "==> [4/5]  Install Electron dependencies"
(cd electron && npm install --prefer-offline 2>/dev/null || npm install)

# ── Step 5: Package with electron-builder ────────────────────────────────────
echo "==> [5/5]  Package Electron app ($PLATFORM) → dist-electron/"
(cd electron && npm run "dist:$PLATFORM")

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done!  Output files:"
case "$PLATFORM" in
  mac)
    ls -1 "$ROOT/dist-electron/"*.dmg      2>/dev/null || true ;;
  linux)
    ls -1 "$ROOT/dist-electron/"*.AppImage 2>/dev/null || true
    ls -1 "$ROOT/dist-electron/"*.deb      2>/dev/null || true
    ls -1 "$ROOT/dist-electron/"*.rpm      2>/dev/null || true ;;
esac
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
