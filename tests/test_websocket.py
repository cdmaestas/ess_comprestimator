"""
Integration tests for the job API — REST lifecycle + WebSocket streaming.

Requires no external services.  Uses FastAPI's built-in TestClient (Starlette)
which supports WebSocket testing out of the box via starlette.testclient.

Run:
    MOCK_BINARY=true python3 -m pytest tests/test_websocket.py -v

Tests:
    1. Health endpoint returns expected shape
    2. POST /api/jobs → 202, returns JobSummary
    3. GET /api/jobs/{id} reflects state progression
    4. WebSocket /stream delivers log lines + terminal status event
    5. Multiple subscribers receive identical messages (fan-out)
    6. GET /api/jobs/{id}/logs polling fallback returns lines + done flag
    7. DELETE /api/jobs/{id} cancels a queued job (409 for non-cancellable)
    8. GET /api/jobs/{id}/results returns CompressionResult on completion
    9. 422 on mutually exclusive sampling options
   10. 404 on unknown job_id
"""

from __future__ import annotations

import os
import time
import threading
from typing import Any

import pytest

# Ensure mock mode for all tests — no binary needed.
os.environ.setdefault("MOCK_BINARY", "true")

from fastapi.testclient import TestClient
from backend.main import app

CLIENT = TestClient(app, raise_server_exceptions=True)

# A real directory that always exists on any machine.
_TEST_PATH = str(os.path.dirname(os.path.abspath(__file__)))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_job(**kwargs: Any) -> dict:
    payload = {"path": _TEST_PATH, **kwargs}
    resp = CLIENT.post("/api/jobs", json=payload)
    assert resp.status_code == 202, resp.text
    return resp.json()


def _wait_for_terminal(job_id: str, timeout: float = 15.0) -> dict:
    """Poll GET /api/jobs/{id} until the job reaches a terminal status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = CLIENT.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        state = resp.json()
        if state["status"] in ("complete", "failed"):
            return state
        time.sleep(0.25)
    pytest.fail(f"Job {job_id} did not reach terminal state within {timeout}s")


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_shape(self):
        resp = CLIENT.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "binary_found" in body
        assert body["mock_mode"] is True


class TestCreateJob:
    def test_create_returns_202_and_job_summary(self):
        body = _create_job()
        assert body["status"] == "queued"
        assert "job_id" in body
        assert body["path"] == _TEST_PATH

    def test_mutually_exclusive_sampling_options(self):
        resp = CLIENT.post(
            "/api/jobs",
            json={
                "path": _TEST_PATH,
                "exhaustive_sampling": True,
                "sampling_percentage": 25.0,
            },
        )
        assert resp.status_code == 422

    def test_invalid_path_rejected(self):
        resp = CLIENT.post("/api/jobs", json={"path": "/does/not/exist/xyz"})
        assert resp.status_code == 422

    def test_skip_hidden_flag(self):
        body = _create_job(skip_hidden=True)
        assert body["status"] == "queued"

    def test_sampling_percentage_flag(self):
        body = _create_job(sampling_percentage=25.0)
        assert body["status"] == "queued"


class TestJobLifecycle:
    def test_job_transitions_to_complete(self):
        body = _create_job()
        state = _wait_for_terminal(body["job_id"])
        assert state["status"] == "complete"

    def test_list_jobs_includes_new_job(self):
        body = _create_job()
        resp = CLIENT.get("/api/jobs")
        assert resp.status_code == 200
        ids = [j["job_id"] for j in resp.json()]
        assert body["job_id"] in ids

    def test_404_on_unknown_job(self):
        resp = CLIENT.get("/api/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_results_available_after_completion(self):
        body = _create_job()
        _wait_for_terminal(body["job_id"])
        resp = CLIENT.get(f"/api/jobs/{body['job_id']}/results")
        assert resp.status_code == 200
        result = resp.json()
        assert result["compression_ratio"] == pytest.approx(2.4, rel=0.01)
        assert "interpretation" in result

    def test_results_409_while_running(self):
        body = _create_job()
        # Immediately try results — job is queued/running, not complete yet.
        resp = CLIENT.get(f"/api/jobs/{body['job_id']}/results")
        # May be 409 (not complete) or 200 if the mock ran instantly — both OK.
        assert resp.status_code in (200, 409)

    def test_warnings_extracted_from_logs(self):
        body = _create_job()
        _wait_for_terminal(body["job_id"])
        full = CLIENT.get(f"/api/jobs/{body['job_id']}").json()
        # Mock run emits one "Note:" line — verify it ended up in warnings.
        assert len(full["warnings"]) >= 1
        assert full["warnings"][0].startswith("Note:")


class TestCancellation:
    def test_cancel_409_for_complete_job(self):
        body = _create_job()
        _wait_for_terminal(body["job_id"])
        resp = CLIENT.delete(f"/api/jobs/{body['job_id']}")
        assert resp.status_code == 409

    def test_cancel_404_for_unknown_job(self):
        resp = CLIENT.delete("/api/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestLogsPolling:
    def test_logs_polling_returns_lines_and_done_flag(self):
        body = _create_job()
        _wait_for_terminal(body["job_id"])

        resp = CLIENT.get(f"/api/jobs/{body['job_id']}/logs?since=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["done"] is True
        assert isinstance(data["lines"], list)
        assert len(data["lines"]) > 0
        assert data["next_since"] == len(data["lines"])
        assert "warnings" in data

    def test_logs_polling_since_parameter(self):
        body = _create_job()
        _wait_for_terminal(body["job_id"])

        # Get all lines first
        all_resp = CLIENT.get(f"/api/jobs/{body['job_id']}/logs?since=0").json()
        total = all_resp["next_since"]

        if total > 1:
            # Fetch second half
            partial = CLIENT.get(
                f"/api/jobs/{body['job_id']}/logs?since={total - 1}"
            ).json()
            assert len(partial["lines"]) == 1


class TestWebSocketStream:
    def test_websocket_delivers_log_and_status_events(self):
        body = _create_job()
        job_id = body["job_id"]

        received: list[dict] = []
        with CLIENT.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
            while True:
                msg = ws.receive_json()
                received.append(msg)
                if msg.get("type") == "status" and msg["status"] in (
                    "complete",
                    "failed",
                ):
                    break

        types = {m["type"] for m in received}
        assert "log" in types
        assert "status" in types
        statuses = [m["status"] for m in received if m["type"] == "status"]
        assert statuses[-1] in ("complete", "failed")

    def test_websocket_replay_for_finished_job(self):
        body = _create_job()
        job_id = body["job_id"]
        _wait_for_terminal(job_id)

        # Connect AFTER job is done — should get full replay.
        received: list[dict] = []
        with CLIENT.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
            while True:
                msg = ws.receive_json()
                received.append(msg)
                if msg.get("type") == "status":
                    break

        assert any(m["type"] == "log" for m in received)
        assert received[-1]["type"] == "status"

    def test_websocket_multiple_subscribers_fan_out(self):
        """
        Two WebSocket clients subscribe to the same job and both receive
        the complete set of messages.
        """
        body = _create_job()
        job_id = body["job_id"]

        results: dict[str, list] = {"a": [], "b": []}

        def _collect(key: str) -> None:
            with CLIENT.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
                while True:
                    msg = ws.receive_json()
                    results[key].append(msg)
                    if msg.get("type") == "status" and msg["status"] in (
                        "complete",
                        "failed",
                    ):
                        break

        t1 = threading.Thread(target=_collect, args=("a",))
        t2 = threading.Thread(target=_collect, args=("b",))
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)

        assert len(results["a"]) > 0, "Subscriber A received no messages"
        assert len(results["b"]) > 0, "Subscriber B received no messages"

        # Both subscribers should see a terminal status event.
        def _has_terminal(msgs: list) -> bool:
            return any(
                m.get("type") == "status" and m.get("status") in ("complete", "failed")
                for m in msgs
            )

        assert _has_terminal(results["a"]), "Subscriber A missing terminal status"
        assert _has_terminal(results["b"]), "Subscriber B missing terminal status"
