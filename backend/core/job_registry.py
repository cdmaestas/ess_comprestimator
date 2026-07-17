"""
In-memory job registry.

All job state lives in a plain Python dict keyed by job_id (UUID string).
State is lost on server restart — acceptable for v1.

Key Phase 2 additions over Phase 1:
  - Fan-out broadcast: each WebSocket subscriber gets its own asyncio.Queue so
    multiple browser tabs can watch the same job without starving each other.
  - Process store: the runner registers the asyncio.Process handle so that
    DELETE /api/jobs/{id} can SIGTERM the subprocess.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from backend.models.job import JobState, JobStatus


_MAX_JOBS = 100  # oldest jobs pruned once this limit is exceeded
_MAX_LOG_LINES = 10_000  # per-job cap; a truncation notice replaces dropped lines


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobState] = {}

        # Fan-out: each job maps to a list of per-subscriber queues.
        # Queue items: {"type": "log", "line": "..."} | {"type": "status", "status": "..."}
        # Sentinel None signals end-of-stream to a subscriber.
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

        # Subprocess handles keyed by job_id — used for cancellation.
        self._procs: Dict[str, asyncio.subprocess.Process] = {}

        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, state: JobState) -> JobState:
        async with self._lock:
            self._jobs[state.job_id] = state
            self._subscribers[state.job_id] = []
            # Prune oldest terminal jobs once we exceed the cap.
            if len(self._jobs) > _MAX_JOBS:
                terminal = [
                    jid
                    for jid, s in self._jobs.items()
                    if s.status.value in ("complete", "failed")
                ]
                for jid in terminal[: len(self._jobs) - _MAX_JOBS]:
                    self._jobs.pop(jid, None)
                    self._subscribers.pop(jid, None)
        return state

    async def get(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

    async def update(self, state: JobState) -> None:
        async with self._lock:
            self._jobs[state.job_id] = state

    async def list_all(self) -> List[JobState]:
        return list(self._jobs.values())

    # ------------------------------------------------------------------
    # Process store (for cancellation)
    # ------------------------------------------------------------------

    def register_proc(self, job_id: str, proc: asyncio.subprocess.Process) -> None:
        self._procs[job_id] = proc

    def deregister_proc(self, job_id: str) -> None:
        self._procs.pop(job_id, None)

    async def cancel_job(self, job_id: str) -> bool:
        """
        Send SIGTERM to the subprocess for job_id.
        Returns True if a signal was sent, False if no process was found.
        """
        proc = self._procs.get(job_id)
        if proc is None:
            return False
        try:
            proc.terminate()  # SIGTERM — allows the child to clean up
        except ProcessLookupError:
            pass  # already exited
        return True

    # ------------------------------------------------------------------
    # Fan-out broadcast helpers
    # ------------------------------------------------------------------

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """
        Register a new subscriber queue for job_id and return it.
        The caller is responsible for calling unsubscribe() when done.
        """
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
        return q

    async def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    async def _broadcast(self, job_id: str, msg: Optional[dict]) -> None:
        """Push a message (or sentinel None) to every subscriber queue."""
        for q in list(self._subscribers.get(job_id, [])):
            await q.put(msg)

    async def push_log(self, job_id: str, line: str) -> None:
        """Append a log line to the job state and broadcast it."""
        state = self._jobs.get(job_id)
        if state is not None:
            if len(state.log_lines) >= _MAX_LOG_LINES:
                # Replace the last line with a truncation notice rather than
                # growing without bound. Subsequent lines are silently dropped.
                if (
                    state.log_lines[-1]
                    != "[...log truncated — output limit reached...]"
                ):
                    state.log_lines.append(
                        "[...log truncated — output limit reached...]"
                    )
                return
            state.log_lines.append(line)
            # Extract accuracy warnings produced by run_comprestimator.py
            if line.startswith("Note:"):
                state.warnings.append(line)
        await self._broadcast(job_id, {"type": "log", "line": line})

    async def push_status(self, job_id: str, status: JobStatus) -> None:
        """Broadcast a status-change event."""
        await self._broadcast(job_id, {"type": "status", "status": status.value})

    async def close_stream(self, job_id: str) -> None:
        """
        Signal end-of-stream by broadcasting sentinel None to all subscribers.
        Clears the subscriber list afterwards (late joiners get replayed history
        from JobState.log_lines via the WebSocket handler).
        """
        await self._broadcast(job_id, None)
        async with self._lock:
            self._subscribers[job_id] = []

    # ------------------------------------------------------------------
    # Concurrency guard
    # ------------------------------------------------------------------

    def running_count(self) -> int:
        return sum(1 for s in self._jobs.values() if s.status == JobStatus.RUNNING)


# Module-level singleton — imported by both the API layer and the runner.
registry = JobRegistry()
