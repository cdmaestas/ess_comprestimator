"""
Tests for the ESS Comprestimator MCP server.

Uses mcp.client._memory.InMemoryTransport to wire a ClientSession directly
to the MCPServer in-process — no subprocess, no network, fast.

InMemoryTransport internally uses anyio task groups, which require anyio's
event loop backend. Each test uses `anyio.run(body)` directly rather than
relying on pytest-asyncio's default asyncio runner, which avoids the
"cancel scope exited in a different task" teardown error.

Run:
    MOCK_BINARY=true python -m pytest tests/test_mcp_server.py -v

All tests run with MOCK_BINARY=true so no compiled Go binary is required.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

import anyio
import pytest

# Must be set before importing backend modules that read config at import time.
os.environ.setdefault("MOCK_BINARY", "true")

from mcp import ClientSession
from mcp.client._memory import InMemoryTransport

from backend.core.job_registry import registry
from backend.mcp_server import server as mcp_server

# ── Helpers ───────────────────────────────────────────────────────────────────

_TEST_PATH = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def _connect():
    """Async context manager: yield an initialised ClientSession."""
    transport = InMemoryTransport(mcp_server)
    async with transport as (read_stream, write_stream):  # noqa: SIM117
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


def _clear_registry():
    registry._jobs.clear()
    registry._subscribers.clear()
    registry._procs.clear()


@pytest.fixture(autouse=True)
def reset_registry():
    _clear_registry()
    yield
    _clear_registry()


# ── Tests: server capabilities ────────────────────────────────────────────────


class TestCapabilities:
    def test_server_info(self):
        async def body():
            async with _connect() as client:
                assert client.server_info is not None
                assert client.server_info.name == "comprestimator"

        anyio.run(body)

    def test_tools_capability_advertised(self):
        async def body():
            async with _connect() as client:
                assert client.server_capabilities.tools is not None

        anyio.run(body)

    def test_resources_capability_advertised(self):
        async def body():
            async with _connect() as client:
                assert client.server_capabilities.resources is not None

        anyio.run(body)

    def test_prompts_capability_advertised(self):
        async def body():
            async with _connect() as client:
                assert client.server_capabilities.prompts is not None

        anyio.run(body)


# ── Tests: tool listing ───────────────────────────────────────────────────────


class TestListTools:
    def test_two_tools_registered(self):
        async def body():
            async with _connect() as client:
                result = await client.list_tools()
                names = {t.name for t in result.tools}
                assert "analyse_path" in names
                assert "list_jobs" in names

        anyio.run(body)

    def test_analyse_path_schema_requires_path(self):
        async def body():
            async with _connect() as client:
                result = await client.list_tools()
                tool = next(t for t in result.tools if t.name == "analyse_path")
                schema = tool.input_schema or {}
                required = schema.get("required", [])
                props = schema.get("properties", {})
                assert "path" in required or "path" in props

        anyio.run(body)

    def test_list_jobs_has_limit_param(self):
        async def body():
            async with _connect() as client:
                result = await client.list_tools()
                tool = next(t for t in result.tools if t.name == "list_jobs")
                props = (tool.input_schema or {}).get("properties", {})
                assert "limit" in props

        anyio.run(body)


# ── Tests: analyse_path tool ──────────────────────────────────────────────────


class TestAnalysePath:
    def test_returns_compression_report(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool("analyse_path", {"path": _TEST_PATH})
                assert not result.is_error
                text = result.content[0].text
                assert "Compression Analysis" in text
                assert "Ratio" in text

        anyio.run(body)

    def test_result_contains_job_id(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool("analyse_path", {"path": _TEST_PATH})
                assert "Job ID" in result.content[0].text

        anyio.run(body)

    def test_mock_ratio_is_2_4x(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool("analyse_path", {"path": _TEST_PATH})
                # Mock runner always produces 2.4x.
                assert "2.400x" in result.content[0].text

        anyio.run(body)

    def test_exhaustive_sampling_flag(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool(
                    "analyse_path", {"path": _TEST_PATH, "exhaustive_sampling": True}
                )
                assert not result.is_error

        anyio.run(body)

    def test_sampling_percentage_flag(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool(
                    "analyse_path", {"path": _TEST_PATH, "sampling_percentage": 25.0}
                )
                assert not result.is_error

        anyio.run(body)

    def test_exclude_patterns_flag(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool(
                    "analyse_path",
                    {"path": _TEST_PATH, "exclude": ["*.log", "node_modules"]},
                )
                assert not result.is_error

        anyio.run(body)

    def test_skip_hidden_flag(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool(
                    "analyse_path", {"path": _TEST_PATH, "skip_hidden": True}
                )
                assert not result.is_error

        anyio.run(body)

    def test_job_is_recorded_in_registry(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                jobs = await registry.list_all()
                assert len(jobs) == 1
                assert jobs[0].request.path == _TEST_PATH

        anyio.run(body)

    def test_completed_job_has_result(self):
        async def body():
            from backend.models.job import JobStatus

            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                jobs = await registry.list_all()
                assert jobs[0].status == JobStatus.COMPLETE
                assert jobs[0].result is not None

        anyio.run(body)


# ── Tests: list_jobs tool ─────────────────────────────────────────────────────


class TestListJobs:
    def test_no_jobs_message(self):
        async def body():
            async with _connect() as client:
                result = await client.call_tool("list_jobs", {})
                assert "No jobs found" in result.content[0].text

        anyio.run(body)

    def test_completed_job_appears(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                result = await client.call_tool("list_jobs", {})
                text = result.content[0].text
                assert "complete" in text
                assert _TEST_PATH in text

        anyio.run(body)

    def test_ratio_appears_in_list(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                result = await client.call_tool("list_jobs", {})
                assert "2.40x" in result.content[0].text

        anyio.run(body)

    def test_limit_parameter_respected(self):
        async def body():
            async with _connect() as client:
                for _ in range(3):
                    await client.call_tool("analyse_path", {"path": _TEST_PATH})
                result = await client.call_tool("list_jobs", {"limit": 1})
                rows = [
                    line
                    for line in result.content[0].text.splitlines()
                    if "complete" in line
                ]
                assert len(rows) == 1

        anyio.run(body)


# ── Tests: resources ──────────────────────────────────────────────────────────


class TestResources:
    def test_no_static_resources_before_any_job(self):
        async def body():
            async with _connect() as client:
                result = await client.list_resources()
                assert result.resources == []

        anyio.run(body)

    def test_job_result_template_is_registered(self):
        async def body():
            async with _connect() as client:
                result = await client.list_resource_templates()
                uris = [t.uri_template for t in result.resource_templates]
                assert any("comprestimator://jobs/" in u for u in uris)

        anyio.run(body)

    def test_read_resource_returns_valid_json(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                jobs = await registry.list_all()
                job_id = jobs[0].job_id
                uri = f"comprestimator://jobs/{job_id}"
                content = await client.read_resource(uri)
                payload = json.loads(content.contents[0].text)
                assert "job_id" in payload
                assert "result" in payload
                assert payload["result"]["compression_ratio"] == pytest.approx(
                    2.4, rel=0.01
                )

        anyio.run(body)

    def test_resource_contains_path(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                jobs = await registry.list_all()
                uri = f"comprestimator://jobs/{jobs[0].job_id}"
                content = await client.read_resource(uri)
                payload = json.loads(content.contents[0].text)
                assert payload["path"] == _TEST_PATH

        anyio.run(body)

    def test_resource_result_fields(self):
        async def body():
            async with _connect() as client:
                await client.call_tool("analyse_path", {"path": _TEST_PATH})
                jobs = await registry.list_all()
                uri = f"comprestimator://jobs/{jobs[0].job_id}"
                content = await client.read_resource(uri)
                res = json.loads(content.contents[0].text)["result"]
                assert "compression_ratio" in res
                assert "interpretation" in res
                assert "initial_size_mb" in res
                assert "compressed_size_mb" in res
                assert "size_reduction_pct" in res
                assert isinstance(res["fcm4_capped"], bool)

        anyio.run(body)


# ── Tests: prompt ─────────────────────────────────────────────────────────────


class TestPrompt:
    def test_compression_advisor_listed(self):
        async def body():
            async with _connect() as client:
                result = await client.list_prompts()
                names = {p.name for p in result.prompts}
                assert "compression_advisor" in names

        anyio.run(body)

    def test_compression_advisor_content(self):
        async def body():
            async with _connect() as client:
                result = await client.get_prompt("compression_advisor", {})
                text = result.messages[0].content.text
                assert "FCM4" in text
                assert "4x" in text
                assert "vdiskset" in text
                assert "provisioning" in text.lower()

        anyio.run(body)

    def test_compression_advisor_has_skipped_guidance(self):
        async def body():
            async with _connect() as client:
                result = await client.get_prompt("compression_advisor", {})
                text = result.messages[0].content.text
                assert "skipped" in text.lower() or "incompressible" in text.lower()

        anyio.run(body)
