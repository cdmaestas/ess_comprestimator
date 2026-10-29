"""
ESS Comprestimator MCP Server
==============================

Exposes the compression estimator as MCP tools, resources, and a prompt so
that an AI agent (Bob, Claude, Codex …) can:

  1. Submit a compression analysis job and wait for the result.
  2. List past jobs and recall their results.
  3. Read a completed job's result as a structured resource.
  4. Use a domain-aware prompt that teaches the agent FCM4 vocabulary.

Transport: stdio (launched by the MCP host as a subprocess).

Run directly:
    .venv/bin/python -m backend.mcp_server

Or via make:
    make mcp
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from backend.core import config
from backend.core.job_registry import registry
from backend.core.runner import run_job
from backend.models.job import JobRequest, JobState, JobStatus, JobSummary
from backend.models.results import CompressionResult

# ── Constants ──────────────────────────────────────────────────────────────────

_SERVER_NAME = "comprestimator"
_SERVER_VERSION = "1.0.0"

# Maximum time (seconds) to wait for a job before returning a "still running"
# message.  Most sampled analyses finish well under 60 s.
_ANALYSE_TIMEOUT_SECS = int(os.environ.get("MCP_ANALYSE_TIMEOUT", "300"))
_POLL_INTERVAL_SECS = 0.5

# ── Startup check ──────────────────────────────────────────────────────────────

if not config.MOCK_BINARY and not os.path.isfile(config.COMPRESTIMATOR_PATH):
    print(
        f"[{_SERVER_NAME}-mcp] ERROR: Go binary not found at "
        f"{config.COMPRESTIMATOR_PATH}. "
        "Run `make` in the repo root to build it, or set MOCK_BINARY=true.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Server ─────────────────────────────────────────────────────────────────────

server = MCPServer(name=_SERVER_NAME, version=_SERVER_VERSION)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _result_to_dict(result: CompressionResult) -> dict[str, Any]:
    return {
        "compression_ratio": result.compression_ratio,
        "interpretation": result.interpretation,
        "initial_size_mb": round(result.initial_size, 3),
        "compressed_size_mb": round(result.compressed_size, 3),
        "size_reduction_pct": round(
            100.0 * (1.0 - result.compressed_size / result.initial_size), 1
        )
        if result.initial_size > 0
        else 0.0,
        "skipped_incompressible_mb": (
            round(result.skipped_bytes_mb, 3)
            if result.skipped_bytes_mb is not None
            else None
        ),
        "fcm4_capped": result.compression_ratio > 4.0,
        "provisioning_note": (
            "FCM4 drives are physically limited to 4x compression. "
            "Use 4x when sizing vdisksets."
            if result.compression_ratio > 4.0
            else None
        ),
    }


def _format_result_md(path: str, result: CompressionResult, job_id: str) -> str:
    d = _result_to_dict(result)
    lines = [
        f"## Compression Analysis: {path}",
        f"**Job ID:** `{job_id}`",
        "",
        f"**Result:** {d['interpretation']}",
        f"**Ratio:** {d['compression_ratio']:.3f}x",
        f"**Size reduction:** {d['size_reduction_pct']}%",
        f"**Sampled data:** {d['initial_size_mb']} MB → {d['compressed_size_mb']} MB",
    ]
    if d["skipped_incompressible_mb"] is not None:
        lines.append(
            f"**Skipped (incompressible):** {d['skipped_incompressible_mb']} MB "
            "(already-compressed or encrypted files excluded from estimate)"
        )
    if d["provisioning_note"]:
        lines.append(f"\n⚠️  {d['provisioning_note']}")
    return "\n".join(lines)


# ── Tool: analyse_path ─────────────────────────────────────────────────────────


@server.tool(
    description=(
        "Submit a compression analysis job for a file or directory and wait for "
        "the result. Returns a structured report: ratio, size reduction, and FCM4 "
        "provisioning guidance. Blocks until complete (up to ~5 minutes for large "
        "exhaustive scans)."
    )
)
async def analyse_path(
    path: str,
    exhaustive_sampling: bool = False,
    sampling_percentage: float | None = None,
    exclude: list[str] | None = None,
    skip_hidden: bool = False,
) -> str:
    """
    path: Absolute path to the file or directory to analyse.
    exhaustive_sampling: Scan every file (most accurate, slowest). Default false.
    sampling_percentage: Percentage of data to sample (0.1–100). Omit for the default 10%.
    exclude: Glob patterns or filenames to skip (e.g. '*.log', 'node_modules').
    skip_hidden: Skip hidden files and directories (names starting with '.'). Default false.
    """
    req = JobRequest(
        path=path,
        exhaustive_sampling=exhaustive_sampling,
        sampling_percentage=sampling_percentage,
        exclude=exclude or [],
        skip_hidden=skip_hidden,
    )

    state = JobState(request=req)
    await registry.create(state)
    job_id = state.job_id

    task = asyncio.create_task(run_job(job_id))

    elapsed = 0.0
    while elapsed < _ANALYSE_TIMEOUT_SECS:
        await asyncio.sleep(_POLL_INTERVAL_SECS)
        elapsed += _POLL_INTERVAL_SECS
        current = await registry.get(job_id)
        if current is None:
            break
        if current.status in (JobStatus.COMPLETE, JobStatus.FAILED):
            break

    task.cancel()

    final = await registry.get(job_id)
    if final is None:
        return f"Job {job_id} disappeared from registry."

    if final.status == JobStatus.COMPLETE and final.result:
        return _format_result_md(path, final.result, job_id)

    if final.status == JobStatus.FAILED:
        return (
            f"Analysis failed for `{path}`.\n\n"
            f"**Error:** {final.error or 'unknown error'}\n\n"
            f"Job ID: `{job_id}`"
        )

    return (
        f"Analysis is still running after {_ANALYSE_TIMEOUT_SECS}s. "
        f"Job ID: `{job_id}`\n\nUse `list_jobs` to check its status later."
    )


# ── Tool: list_jobs ────────────────────────────────────────────────────────────


@server.tool(
    description=(
        "List recent compression analysis jobs with their status and ratio. "
        "Use this to recall past results without re-running the analysis."
    )
)
async def list_jobs(limit: int = 10) -> str:
    """
    limit: Maximum number of jobs to return (newest first). Default 10.
    """
    all_states = await registry.list_all()
    sorted_states = sorted(all_states, key=lambda s: s.created_at, reverse=True)
    jobs = [JobSummary.from_state(s) for s in sorted_states[:limit]]

    if not jobs:
        return "No jobs found."

    rows = ["| Job ID | Path | Status | Ratio |", "|--------|------|--------|-------|"]
    for j in jobs:
        ratio = f"{j.compression_ratio:.2f}x" if j.compression_ratio else "—"
        rows.append(f"| `{j.job_id[:8]}…` | {j.path} | {j.status.value} | {ratio} |")

    return "\n".join(rows)


# ── Resource: completed job result ─────────────────────────────────────────────


@server.resource(
    uri="comprestimator://jobs/{job_id}",
    name="Compression job result",
    description="Full structured result for a completed compression analysis job.",
    mime_type="application/json",
)
async def job_result_resource(job_id: str) -> str:
    state = await registry.get(job_id)
    if state is None or state.result is None:
        raise ValueError(f"No completed result for job {job_id}")
    payload = {
        "job_id": job_id,
        "path": state.request.path,
        "status": state.status.value,
        "result": _result_to_dict(state.result),
    }
    return json.dumps(payload, indent=2)


# ── Prompt: compression_advisor ────────────────────────────────────────────────

_ADVISOR_PROMPT = """\
You are an expert in IBM ESS (Elastic Storage Server) storage planning and FCM4 compression.

## Key concepts

- **FCM4 drives** achieve compression in hardware. The physical limit is **4x** — data that
  compresses beyond 4x still fits, but you must provision vdisksets as if the ratio is 4x.
- **Compression ratio** is expressed as original_size / compressed_size. A ratio of 2.4x means
  the data compresses to ~42% of its original footprint.
- **Sampled analysis**: by default the tool samples 10% of the data. For directories under 1 GB
  consider exhaustive sampling for higher accuracy.
- **Skipped (incompressible) data**: files like .zip, .jpg, .mp4, or encrypted volumes resist
  compression. The tool reports the skipped volume separately. If a large fraction is skipped,
  the reported ratio may be optimistic for the full dataset.
- **Provisioning formula**: if you have D TB of raw data and a compression ratio of R (capped
  at 4x), you need at minimum D / R TB of FCM4 physical capacity.

## How to respond

1. State the compression ratio and its plain-English interpretation (Excellent / Good / Moderate / Low).
2. If skipped data is significant (>20% of sampled volume), flag it and adjust expectations.
3. If ratio > 4x, remind the user to use 4x for vdiskset provisioning.
4. Provide a concrete provisioning recommendation if the user mentioned a dataset size.
5. Suggest exhaustive sampling or a larger percentage if accuracy is important.
"""


@server.prompt(
    description=(
        "Inject FCM4/ESS domain knowledge so the agent interprets compression "
        "results accurately and gives provisioning guidance."
    )
)
def compression_advisor() -> str:
    return _ADVISOR_PROMPT


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"[{_SERVER_NAME}-mcp] starting on stdio", file=sys.stderr)
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
