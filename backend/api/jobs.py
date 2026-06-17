"""
Job API — REST + WebSocket endpoints.

REST:
    POST   /api/jobs                          create & enqueue a job
    GET    /api/jobs                          list all jobs (summaries)
    GET    /api/jobs/{job_id}                 full job state
    GET    /api/jobs/{job_id}/results         parsed CompressionResult (complete only)
    GET    /api/jobs/{job_id}/results.csv     downloadable CSV of the result
    GET    /api/jobs/{job_id}/logs?since=N    polling fallback for proxy-hostile networks
    DELETE /api/jobs/{job_id}                 cancel a running job (SIGTERM)

WebSocket:
    WS     /api/jobs/{job_id}/stream          live log + status events (fan-out safe)
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from backend.core import config
from backend.core.job_registry import registry
from backend.core.runner import run_job
from backend.models.job import JobRequest, JobState, JobStatus, JobSummary
from backend.models.results import CompressionResult

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _validate_request(req: JobRequest) -> None:
    if req.exhaustive_sampling and req.sampling_percentage is not None:
        raise HTTPException(
            status_code=422,
            detail="exhaustive_sampling and sampling_percentage are mutually exclusive",
        )

    # Resolve to a canonical absolute path (follows symlinks, verifies existence).
    # Overwrites req.path so the rest of the pipeline sees the real path, not a
    # symlink or relative reference that could resolve differently in the subprocess.
    try:
        import pathlib
        real = pathlib.Path(req.path).resolve(strict=True)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Path does not exist or cannot be resolved: {req.path}",
        )

    if not real.is_file() and not real.is_dir():
        raise HTTPException(
            status_code=422,
            detail="Path must point to a regular file or directory",
        )

    # Confine analysis to directories the local user owns or that are explicitly
    # intended for user data. This prevents another local process or a malicious
    # localhost request from probing sensitive system paths like /etc or /root.
    import pathlib as _pl
    _allowed = [_pl.Path.home()]
    for _extra in ("/Volumes", "/media", "/mnt", "/tmp", "/private/tmp"):
        _p = _pl.Path(_extra)
        if _p.exists():
            _allowed.append(_p)

    real_str = str(real)
    if not any(real_str == str(root) or real_str.startswith(str(root) + "/")
               for root in _allowed):
        raise HTTPException(
            status_code=403,
            detail=(
                "Path is outside the allowed analysis roots "
                "(home directory, /Volumes, /media, /mnt, /tmp). "
                "Only user-owned locations may be analysed."
            ),
        )

    req.path = str(real)


async def _check_capacity() -> None:
    if registry.running_count() >= config.MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Server is at capacity ({config.MAX_CONCURRENT_JOBS} concurrent jobs). "
                "Please wait for a running job to finish."
            ),
        )


async def _get_or_404(job_id: str) -> JobState:
    state = await registry.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return state


# ──────────────────────────────────────────────────────────────────────────────
# REST — job lifecycle
# ──────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=JobSummary, status_code=202)
async def create_job(req: JobRequest, background_tasks: BackgroundTasks) -> JobSummary:
    """
    Validate parameters, create a job, enqueue it, and return immediately (202).
    Track progress via GET /api/jobs/{job_id} (polling) or WS /api/jobs/{job_id}/stream.
    """
    _validate_request(req)
    await _check_capacity()

    state = JobState(request=req)
    await registry.create(state)
    background_tasks.add_task(run_job, state.job_id)

    return JobSummary.from_state(state)


@router.get("", response_model=List[JobSummary])
async def list_jobs() -> List[JobSummary]:
    """Return summary rows for all jobs, newest first."""
    all_jobs = await registry.list_all()
    return [
        JobSummary.from_state(s)
        for s in sorted(all_jobs, key=lambda s: s.created_at, reverse=True)
    ]


@router.get("/{job_id}", response_model=JobState, response_model_exclude={"pid"})
async def get_job(job_id: str) -> JobState:
    """Return full job state including all captured log lines."""
    return await _get_or_404(job_id)


@router.delete("/{job_id}", status_code=202)
async def cancel_job(job_id: str) -> JSONResponse:
    """
    Cancel a running job by sending SIGTERM to its subprocess.
    Idempotent: cancelling a queued, complete, or already-failed job returns 409.
    """
    state = await _get_or_404(job_id)

    if state.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel a job with status '{state.status.value}'",
        )

    sent = await registry.cancel_job(job_id)
    if not sent:
        # No subprocess yet — job is QUEUED (or process already gone).
        # Set the cancellation flag so run_job aborts before starting work.
        state.cancelled = True
        state.status = JobStatus.FAILED
        state.error = "Cancelled by user"
        await registry.update(state)

    return JSONResponse(
        content={"job_id": job_id, "detail": "Cancellation signal sent"},
        status_code=202,
    )


# ──────────────────────────────────────────────────────────────────────────────
# REST — results
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{job_id}/results.csv")
async def download_results_csv(job_id: str) -> StreamingResponse:
    """
    Download the compression result as a CSV file.

    Generated on demand from the stored CompressionResult — the original
    results.csv written by the binary is deleted after a successful run.
    """
    state = await _get_or_404(job_id)
    if state.status != JobStatus.COMPLETE or state.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not complete (status: {state.status.value})",
        )

    r = state.result
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([
        "job_id", "path", "status",
        "created_at", "started_at", "completed_at",
        "compression_ratio", "initial_size_bytes", "compressed_size_bytes",
        "size_reduction_pct",
        "num_zero_blocks", "num_non_zero_blocks", "total_blocks_read",
        "conf_comp", "conf_zeros",
        "dev_size_mb", "after_zero_size", "after_zero_perc",
        "after_rtc_size", "after_rtc_perc",
        "error_value", "tot_time_s",
        "interpretation",
    ])

    reduction_pct = (
        round((1 - r.compressed_size / r.initial_size) * 100, 2)
        if r.initial_size > 0 else None
    )

    writer.writerow([
        job_id,
        state.request.path,
        state.status.value,
        state.created_at.isoformat(),
        state.started_at.isoformat() if state.started_at else "",
        state.completed_at.isoformat() if state.completed_at else "",
        r.compression_ratio,
        r.initial_size,
        r.compressed_size,
        reduction_pct,
        r.num_zero_blocks,
        r.num_non_zero_blocks,
        r.total_blocks_read,
        r.conf_comp,
        r.conf_zeros,
        r.dev_size_mb,
        r.after_zero_size,
        r.after_zero_perc,
        r.after_rtc_size,
        r.after_rtc_perc,
        r.error,
        r.tot_time,
        r.interpretation,
    ])

    buf.seek(0)
    filename = f"comprestimator_{job_id[:8]}.csv"
    return StreamingResponse(
        iter([buf.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/results", response_model=CompressionResult)
async def get_results(job_id: str) -> CompressionResult:
    """Return the parsed compression result for a completed job."""
    state = await _get_or_404(job_id)
    if state.status == JobStatus.FAILED:
        raise HTTPException(status_code=422, detail=f"Job failed: {state.error}")
    if state.status != JobStatus.COMPLETE or state.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not yet complete (status: {state.status.value})",
        )
    return state.result


# ──────────────────────────────────────────────────────────────────────────────
# REST — log polling fallback
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{job_id}/logs")
async def get_logs(
    job_id: str,
    since: int = Query(0, ge=0, description="Return only log lines at index >= since"),
) -> JSONResponse:
    """
    Polling fallback for environments where WebSocket connections are blocked
    (e.g. enterprise HTTP proxies).

    Call repeatedly with `since` set to the number of lines already received.
    When the job finishes the response includes `"done": true` so the caller
    can stop polling.

    Example:
        GET /api/jobs/{id}/logs?since=0   → first batch
        GET /api/jobs/{id}/logs?since=12  → lines 12-N
    """
    state = await _get_or_404(job_id)
    lines = state.log_lines[since:]
    done = state.status in (JobStatus.COMPLETE, JobStatus.FAILED)
    return JSONResponse(
        content={
            "job_id": job_id,
            "status": state.status.value,
            "lines": lines,
            "next_since": since + len(lines),
            "done": done,
            "warnings": state.warnings if done else [],
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket — live stream (fan-out safe)
# ──────────────────────────────────────────────────────────────────────────────

@router.websocket("/{job_id}/stream")
async def stream_job(websocket: WebSocket, job_id: str) -> None:
    """
    Stream log lines and status events for a running job.

    Multiple browser tabs can connect simultaneously — each gets its own
    queue and receives all messages independently.

    Message schema:
        {"type": "log",     "line": "<text>"}
        {"type": "status",  "status": "running"|"complete"|"failed"}
        {"type": "ping"}                           ← keepalive every 30 s

    The stream closes automatically when the job finishes.
    If the job is already done when the client connects, stored log lines are
    replayed immediately and the connection closes.
    """
    state = await registry.get(job_id)
    if state is None:
        await websocket.close(code=4004, reason=f"Job {job_id!r} not found")
        return

    await websocket.accept()

    # ── Replay finished jobs immediately ──────────────────────────────────────
    if state.status in (JobStatus.COMPLETE, JobStatus.FAILED):
        for line in state.log_lines:
            await websocket.send_json({"type": "log", "line": line})
        await websocket.send_json({"type": "status", "status": state.status.value})
        await websocket.close()
        return

    # ── Subscribe to the fan-out broadcast ────────────────────────────────────
    q = await registry.subscribe(job_id)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue

            if msg is None:
                # Sentinel: runner has closed the stream.
                break

            await websocket.send_json(msg)

            if msg.get("type") == "status" and msg.get("status") in (
                JobStatus.COMPLETE.value,
                JobStatus.FAILED.value,
            ):
                break

    except WebSocketDisconnect:
        pass
    finally:
        await registry.unsubscribe(job_id, q)
        try:
            await websocket.close()
        except Exception:
            pass
