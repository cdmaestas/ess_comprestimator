"""
Async job runner — v2 (Go binary).

Calls the ess_comprestimator Go binary directly and parses results from its
stdout, replacing the old Python-wrapper + CSV approach.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.core import config
from backend.core.job_registry import registry
from backend.models.job import JobState, JobStatus
from backend.models.results import CompressionResult

# Semaphore enforcing MAX_CONCURRENT_JOBS — created lazily.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
    return _semaphore


def _build_cli_args(state: JobState) -> list[str]:
    """Translate JobRequest fields into ess_comprestimator v2 CLI arguments."""
    req = state.request
    args = [config.COMPRESTIMATOR_PATH, "--path", req.path]

    if req.exhaustive_sampling:
        args.append("--exhaustive-sample")
    elif req.sampling_percentage is not None:
        # v2 flag takes an integer, no % suffix
        args += ["--sampling-percentage", str(int(req.sampling_percentage))]

    if req.skip_hidden:
        args.append("--exclude-hidden")

    for pattern in (req.exclude or []):
        args += ["--exclude", pattern]

    return args


async def _mock_run(state: JobState) -> None:
    """Synthetic run — enabled via MOCK_BINARY=true."""
    lines = [
        "-- IBM ESS Comprestimator v2.0.0 --------",
        "",
        "[MOCK] Mapping directory | 128.00 MB found so far (0 files were not read)",
        "[MOCK] Running compression on sample…",
        "",
        "-- Comprestimator Results ---------------",
        "Estimated Compression Ratio 2.400x",
        "Pre-compression size: 128.00 MB",
        "Post-compression size: 53.33 MB",
        "",
        "Note: FCM4 drives are limited to 4x physical space. Use a compression ratio of 4x when provisioning vdisksets.",
    ]
    for line in lines:
        await registry.push_log(state.job_id, line)
        await asyncio.sleep(0.4)

    state.result = CompressionResult(
        initial_size=128.0,
        compressed_size=53.33,
        compression_ratio=2.4,
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

        try:
            if config.MOCK_BINARY:
                await _mock_run(state)

            else:
                # ── Validate binary ────────────────────────────────────────────
                if not os.path.isfile(config.COMPRESTIMATOR_PATH):
                    raise FileNotFoundError(
                        f"Go binary not found at {config.COMPRESTIMATOR_PATH}. "
                        "Run `make` in the repo root first."
                    )

                cli_args = _build_cli_args(state)

                # ── Spawn subprocess ───────────────────────────────────────────
                proc = await asyncio.create_subprocess_exec(
                    *cli_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # merge for a unified log
                )

                # Store handle + PID so DELETE /api/jobs/{id} can cancel it.
                registry.register_proc(job_id, proc)
                state.pid = proc.pid
                await registry.update(state)

                # ── Stream output line-by-line ─────────────────────────────────
                output_lines: list[str] = []
                assert proc.stdout is not None
                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace").rstrip("\r\n")
                    # The Go binary uses \r for in-place progress updates;
                    # keep only the last "frame" so the log shows clean lines.
                    if "\r" in line:
                        line = line.split("\r")[-1].strip()
                    if line:
                        await registry.push_log(job_id, line)
                        output_lines.append(line)

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

                # ── Parse results from accumulated stdout ──────────────────────
                state.result = CompressionResult.from_stdout("\n".join(output_lines))

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
            await registry.close_stream(job_id)
