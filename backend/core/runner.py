"""
Async job runner — Phase 2.

Changes from Phase 1:
  - Registers the asyncio.Process handle with the registry so DELETE /api/jobs/{id}
    can SIGTERM the subprocess.
  - Stores proc.pid in JobState for API responses.
  - Uses registry.close_stream() (was close_queue()) to close the fan-out broadcast.
  - Cancellation (CancelledError / process exit code -15) transitions job to FAILED
    with a descriptive "cancelled by user" message.
  - MOCK_BINARY mode preserved for macOS development.
"""

from __future__ import annotations

import asyncio
import csv
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.core import config
from backend.core.job_registry import registry
from backend.models.job import JobState, JobStatus
from backend.models.results import CompressionResult

# Absolute path to run_comprestimator.py.
# In a PyInstaller frozen bundle __file__ lives inside sys._MEIPASS, so
# parents[2] resolves there — which is also where we bundle the script.
# In normal (source) mode parents[2] is the repo root.
_SCRIPT_PATH = str(
    (Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2])
    / "run_comprestimator.py"
)


def _get_python_exe() -> str:
    """Return a real Python interpreter path.

    In a PyInstaller bundle sys.executable is the frozen binary itself — running
    it with a script argument would re-execute backend_entry.py (starting a new
    uvicorn server) instead of the intended script.  Use the system Python3
    instead, which macOS ships at /usr/bin/python3 via Xcode Command Line Tools.
    """
    if getattr(sys, "frozen", False):
        import shutil
        python = shutil.which("python3") or shutil.which("python")
        if not python:
            raise RuntimeError(
                "No Python 3 interpreter found on PATH. "
                "Install Python 3 (https://python.org) to run jobs."
            )
        return python
    return sys.executable

# Semaphore enforcing MAX_CONCURRENT_JOBS — created lazily.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
    return _semaphore


def _build_cli_args(state: JobState) -> list[str]:
    """Translate JobRequest fields into run_comprestimator.py CLI arguments."""
    req = state.request
    args = [_get_python_exe(), "-u", _SCRIPT_PATH, "--path", req.path]

    if req.exhaustive_sampling:
        args.append("--exhaustive-sampling")
    elif req.sampling_percentage is not None:
        args += ["--sampling-percentage", f"{req.sampling_percentage}%"]

    if req.skip_nested_directories:
        args.append("--skip-nested-directories")

    if req.skip_hidden:
        args.append("--skip-hidden")

    if req.exclude:
        args += ["--exclude"] + req.exclude

    return args


def _parse_results(results_csv: str) -> CompressionResult:
    """Read the last data row from results.csv and return a CompressionResult."""
    with open(results_csv, newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError("results.csv is empty")
    return CompressionResult.from_csv_row(rows[-1])


async def _mock_run(state: JobState) -> None:
    """Synthetic run — enabled via MOCK_BINARY=true."""
    lines = [
        "[MOCK] Simulating comprestimator run…",
        "[MOCK] Directory scan complete — 42 files, 128 MB total",
        "[MOCK] Using WEIGHTED sampling strategy",
        "[MOCK] Added /some/file.dat with size 4096000 ; current archive is 4096000 bytes",
        "[MOCK] Running comprestimator on archive…",
        "[MOCK] Comprestimator finished!",
        "Note: < 5% of files in the directory were sampled due to a low sampling percentage.",
    ]
    for line in lines:
        await registry.push_log(state.job_id, line)
        await asyncio.sleep(0.8)

    state.result = CompressionResult(
        initial_size=128.0,       # MB — matches real binary output unit
        compressed_size=53.33,    # MB
        compression_ratio=2.4,
        num_zero_blocks=1024,
        num_non_zero_blocks=65_536,
        total_blocks_read=66_560,
        conf_comp=0.001,
        conf_zeros=0.001,
        interpretation="2.40x — Good compression candidate",
    )


async def run_job(job_id: str) -> None:
    """
    Main async entry point — called as an asyncio BackgroundTask from the API.

    Lifecycle:  QUEUED → RUNNING → COMPLETE | FAILED | CANCELLED
    """
    state = await registry.get(job_id)
    if state is None:
        return

    sem = _get_semaphore()
    async with sem:
        # Abort immediately if a cancel request arrived while we were queued.
        if state.cancelled:
            await registry.close_stream(job_id)
            return

        # ── Transition to RUNNING ──────────────────────────────────────────────
        state.status = JobStatus.RUNNING
        state.started_at = datetime.now(timezone.utc)
        await registry.update(state)
        await registry.push_status(job_id, JobStatus.RUNNING)

        work_dir: str | None = None
        try:
            # ── Isolated working directory ─────────────────────────────────────
            os.makedirs(config.RESULTS_BASE_DIR, exist_ok=True)
            work_dir = tempfile.mkdtemp(
                prefix=f"job_{job_id[:8]}_", dir=config.RESULTS_BASE_DIR
            )
            results_csv = os.path.join(work_dir, "results.csv")

            if config.MOCK_BINARY:
                await _mock_run(state)

            else:
                # ── Validate binary ────────────────────────────────────────────
                if not os.path.isfile(config.COMPRESTIMATOR_PATH):
                    raise FileNotFoundError(
                        f"Compiled binary not found at {config.COMPRESTIMATOR_PATH}. "
                        "Run `make` in the repo root first."
                    )

                cli_args = _build_cli_args(state)
                env = {
                    **os.environ,
                    # These are now read by run_comprestimator.py (Phase 2 patch).
                    "COMPRESTIMATOR_PATH": config.COMPRESTIMATOR_PATH,
                    "COMPRESTIMATOR_RESULTS_PATH": results_csv,
                }

                # ── Spawn subprocess ───────────────────────────────────────────
                proc = await asyncio.create_subprocess_exec(
                    *cli_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # merge for a unified log
                    cwd=work_dir,
                    env=env,
                )

                # Store handle + PID so DELETE /api/jobs/{id} can cancel it.
                registry.register_proc(job_id, proc)
                state.pid = proc.pid
                await registry.update(state)

                # ── Stream output line-by-line ─────────────────────────────────
                assert proc.stdout is not None
                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace").rstrip()
                    await registry.push_log(job_id, line)

                await proc.wait()
                registry.deregister_proc(job_id)
                state.pid = None

                # Return code -15 = SIGTERM (user cancelled)
                if proc.returncode == -15:
                    raise RuntimeError("Job cancelled by user")
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"comprestimator exited with code {proc.returncode}"
                    )

                # ── Parse results ──────────────────────────────────────────────
                state.result = _parse_results(results_csv)

            # ── Transition to COMPLETE ─────────────────────────────────────────
            state.status = JobStatus.COMPLETE
            state.completed_at = datetime.now(timezone.utc)
            await registry.update(state)
            await registry.push_status(job_id, JobStatus.COMPLETE)

        except Exception as exc:  # noqa: BLE001
            state.status = JobStatus.FAILED
            state.error = str(exc)
            state.completed_at = datetime.now(timezone.utc)
            registry.deregister_proc(job_id)
            state.pid = None
            await registry.update(state)
            await registry.push_log(job_id, f"[ERROR] {exc}")
            await registry.push_status(job_id, JobStatus.FAILED)

        finally:
            # Close the fan-out broadcast so all WebSocket handlers exit cleanly.
            await registry.close_stream(job_id)

            # Always remove the work dir — it may contain sampled file content
            # (the tar archive) that should not persist on disk after the job ends.
            if work_dir:
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass
