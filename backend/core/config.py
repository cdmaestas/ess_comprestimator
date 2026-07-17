"""
Application configuration — reads from environment variables with sensible defaults.

Override any value at runtime via environment or a .env file:
    COMPRESTIMATOR_PATH=/app/comprestimator uvicorn backend.main:app
"""

import os
from pathlib import Path


def _get_comprestimator_path() -> str:
    env_path = os.environ.get("COMPRESTIMATOR_PATH")
    if env_path:
        return env_path
    return str(Path(__file__).resolve().parents[2] / "ess_comprestimator")


def _get_max_concurrent_jobs() -> int:
    raw = os.environ.get("MAX_CONCURRENT_JOBS", "3")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"MAX_CONCURRENT_JOBS must be an integer, got {raw!r}"
        )
    if value < 1:
        raise ValueError(
            f"MAX_CONCURRENT_JOBS must be >= 1, got {value}"
        )
    return value


# Absolute path to the compiled Go binary.
# In packaged app: set by Electron via COMPRESTIMATOR_PATH env var.
# In development: defaults to ./ess_comprestimator (repo root).
COMPRESTIMATOR_PATH: str = _get_comprestimator_path()

# Maximum number of jobs allowed to run concurrently.
MAX_CONCURRENT_JOBS: int = _get_max_concurrent_jobs()

# When True the runner returns a synthetic result without invoking the binary.
# Useful for frontend development where the Go binary is unavailable.
MOCK_BINARY: bool = os.environ.get("MOCK_BINARY", "").lower() in ("1", "true", "yes")
