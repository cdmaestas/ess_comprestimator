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

# Patterns emitted by the minlz compression library — not useful to display.
_MINLZ_PATTERNS = ("Separator is not found", "chunk exceed", "[ERROR]")


def _is_minlz_error(line: str) -> bool:
    return any(p in line for p in _MINLZ_PATTERNS)


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
                    stderr=asyncio.subprocess.PIPE,  # capture stderr separately to filter errors
                )

                # Store handle so DELETE /api/jobs/{id} can send SIGTERM.
                registry.register_proc(job_id, proc)
                await registry.update(state)

                # ── Stream output line-by-line ─────────────────────────────────
                output_lines: list[str] = []
                assert proc.stdout is not None
                assert proc.stderr is not None
                
                # Read stdout byte-by-byte to capture \r-terminated progress updates
                async def read_stdout():
                    buffer = bytearray()
                    last_progress_line = ""
                    while True:
                        chunk = await proc.stdout.read(1)
                        if not chunk:
                            break
                        
                        buffer.extend(chunk)
                        
                        # Process on \n or \r
                        if chunk in (b'\n', b'\r'):
                            if buffer:
                                line = buffer.decode(errors="replace").strip()
                                if line:
                                    output_lines.append(line)
                                    
                                    # Skip minlz errors
                                    if _is_minlz_error(line):
                                        buffer.clear()
                                        continue
                                    
                                    # For progress lines (with \r), only send if content changed
                                    # Progress lines contain "Ratio:" or "Progress"
                                    is_progress = "Ratio:" in line or "Progress" in line
                                    
                                    if chunk == b'\r' and is_progress:
                                        # Only send if different from last progress line
                                        if line != last_progress_line:
                                            await registry.push_log(job_id, line)
                                            last_progress_line = line
                                    else:
                                        # Regular line with \n - always send
                                        await registry.push_log(job_id, line)
                                        last_progress_line = ""  # Reset progress tracking
                                
                                buffer.clear()
                
                async def read_stderr():
                    async for raw_line in proc.stderr:
                        line = raw_line.decode(errors="replace").rstrip("\r\n")
                        # Accumulate stderr for debugging but don't display minlz errors
                        if line:
                            output_lines.append(f"[STDERR] {line}")
                        # Filter out minlz library errors and error log notifications from UI
                        if _is_minlz_error(line) or "Error log created at" in line:
                            continue
                        if line:
                            await registry.push_log(job_id, f"[STDERR] {line}")
                
                await asyncio.gather(read_stdout(), read_stderr())
                await proc.wait()
                registry.deregister_proc(job_id)

                # Check exit status
                if proc.returncode == -15:
                    raise RuntimeError("Job cancelled by user")
                
                # Check if binary produced results section (even if exit code is 0)
                full_output = "\n".join(output_lines)
                has_results = "-- Comprestimator Results" in full_output
                
                if proc.returncode != 0 or not has_results:
                    # Binary failed or exited early without results
                    output_sample = "\n".join(output_lines[-15:]) if output_lines else "(no output)"
                    
                    if not has_results and "Mapping directory" in full_output:
                        # Binary stopped during directory mapping phase
                        raise RuntimeError(
                            f"Binary stopped during directory scan (exit code {proc.returncode}). "
                            f"Check path permissions and exclude patterns.\n{output_sample}"
                        )
                    elif proc.returncode != 0:
                        raise RuntimeError(
                            f"Binary exited with code {proc.returncode}.\n{output_sample}"
                        )
                    else:
                        raise RuntimeError(
                            f"Binary completed but produced no results.\n{output_sample}"
                        )
                
                # Parse results from output
                state.result = CompressionResult.from_stdout(full_output)

            # ── Transition to COMPLETE ─────────────────────────────────────────
            state.status = JobStatus.COMPLETE
            state.completed_at = datetime.now(timezone.utc)
            await registry.update(state)
            await registry.push_status(job_id, JobStatus.COMPLETE)

        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            
            # Categorize failure for clearer diagnostics
            if "Could not find compression results" in error_msg:
                # Binary ran but produced no results section
                output_sample = "\n".join(output_lines[-15:]) if output_lines else "(no output)"
                
                # Check for common causes
                if any("0 files" in line or "no files" in line.lower() for line in output_lines):
                    state.error = "No files found to compress (check exclude patterns and permissions)"
                elif any("error" in line.lower() for line in output_lines):
                    state.error = "Binary encountered errors during execution (check error log)"
                else:
                    state.error = "Binary completed but produced no compression results"
                
                await registry.push_log(job_id, f"[ERROR] {state.error}")
                await registry.push_log(job_id, f"[DEBUG] Full output:\n{output_sample}")
            elif "Separator is not found" in error_msg or "chunk exceed" in error_msg:
                state.error = f"Compression library warning: {error_msg}"
            else:
                await registry.push_log(job_id, f"[ERROR] {error_msg}")
                state.error = error_msg
            
            state.status = JobStatus.FAILED
            state.completed_at = datetime.now(timezone.utc)
            registry.deregister_proc(job_id)
            await registry.update(state)
            await registry.push_status(job_id, JobStatus.FAILED)

        finally:
            await registry.close_stream(job_id)
