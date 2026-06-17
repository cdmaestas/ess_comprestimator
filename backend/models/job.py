"""
Pydantic models for job lifecycle management.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.results import CompressionResult


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class JobRequest(BaseModel):
    """Parameters submitted by the user to create a new job."""

    path: str = Field(..., description="Absolute path to the file or directory to analyse")

    exhaustive_sampling: bool = Field(
        False,
        description="Sample the entire directory (most accurate, slowest)",
    )
    sampling_percentage: Optional[float] = Field(
        None,
        ge=0.1,
        le=100.0,
        description="Percentage of directory size to sample (0.1–100). "
                    "Mutually exclusive with exhaustive_sampling.",
    )
    exclude: List[str] = Field(
        default_factory=list,
        description="Glob patterns / filenames to exclude from sampling",
    )

    @field_validator("exclude")
    @classmethod
    def _no_flag_like_patterns(cls, v: List[str]) -> List[str]:
        for pattern in v:
            if pattern.startswith("-"):
                raise ValueError(
                    f"Exclude pattern may not start with '-' (would be interpreted as a "
                    f"CLI flag by the subprocess): {pattern!r}"
                )
        return v
    skip_nested_directories: bool = Field(
        False,
        description="Only sample files directly inside the target directory",
    )
    skip_hidden: bool = Field(
        False,
        description="Skip hidden files and directories (names starting with '.')",
    )

    @field_validator("sampling_percentage")
    @classmethod
    def exclusive_with_exhaustive(cls, v: Optional[float]) -> Optional[float]:
        # Cross-field validation is done in the API layer where both fields are visible.
        return v


class JobState(BaseModel):
    """Full server-side state of a job, including mutable runtime fields."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: JobRequest

    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Accumulated stdout/stderr lines from the subprocess
    log_lines: List[str] = Field(default_factory=list)

    # "Note:" accuracy warnings extracted from stdout by the registry
    warnings: List[str] = Field(default_factory=list)

    # Error message when status == FAILED
    error: Optional[str] = None

    # Set to True when a cancel request arrives before the subprocess starts.
    # run_job checks this after acquiring the semaphore and aborts early.
    cancelled: bool = False

    # PID of the subprocess — stored so the API can send SIGTERM for cancellation.
    # None when the job is queued or after the process exits.
    pid: Optional[int] = None

    # Populated when status == COMPLETE
    result: Optional[CompressionResult] = None

    model_config = ConfigDict(frozen=False)


class JobSummary(BaseModel):
    """Lightweight job representation for list endpoints."""

    job_id: str
    status: JobStatus
    path: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    compression_ratio: Optional[float] = None

    @classmethod
    def from_state(cls, state: JobState) -> "JobSummary":
        return cls(
            job_id=state.job_id,
            status=state.status,
            path=state.request.path,
            created_at=state.created_at,
            started_at=state.started_at,
            completed_at=state.completed_at,
            compression_ratio=(
                state.result.compression_ratio if state.result else None
            ),
        )
