"""
Application configuration — reads from environment variables with sensible defaults.

Override any value at runtime via environment or a .env file:
    COMPRESTIMATOR_PATH=/app/comprestimator uvicorn backend.main:app
"""

import os
from pathlib import Path

# Absolute path to the compiled Go binary.
# In packaged app: set by Electron via COMPRESTIMATOR_PATH env var
# In development: defaults to ./ess_comprestimator (repo root)
def _get_comprestimator_path() -> str:
    # First check environment variable (set by Electron in packaged app)
    env_path = os.environ.get("COMPRESTIMATOR_PATH")
    if env_path:
        return env_path
    
    # Development fallback: repo root
    return str(Path(__file__).resolve().parents[2] / "ess_comprestimator")

COMPRESTIMATOR_PATH: str = _get_comprestimator_path()

# Base directory under which per-job temp directories are created.
RESULTS_BASE_DIR: str = os.environ.get(
    "RESULTS_BASE_DIR",
    str(Path(os.environ.get("TMPDIR", "/tmp")) / "comprestimator_jobs"),
)

# Maximum number of jobs allowed to run concurrently.
MAX_CONCURRENT_JOBS: int = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))

# When True the runner returns a synthetic result without invoking the binary.
# Useful for frontend development on macOS where the Linux binary is unavailable.
MOCK_BINARY: bool = os.environ.get("MOCK_BINARY", "").lower() in ("1", "true", "yes")
