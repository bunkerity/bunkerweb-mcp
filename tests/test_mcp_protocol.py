"""Exercise the installed SDK over HTTP and stdio, with no upstream services."""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.exceptions import BunkerWebError
from bunkerweb_mcp.main import create_app
from bunkerweb_mcp.schemas.core import PingResponse
from bunkerweb_mcp.search_client import SearchClient, SearchResult

INITIALIZE = {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {"name": "migration-test", "version": "1.0"},
}


@pytest.mark.asyncio
async def test_http_protocol_auth_security_resources_and_search(monkeypatch, tmp_path):
    (tmp_path / "api.log").write_text("ready\n")
    settings = Settings(
        BUNKERWEB_LOGS_PATH=tmp_path,
        BUNKERWEB_WEBSOCKET_TOKEN="test-token",
        MCP_ALLOWED_HOSTS=" localhost, localhost:8080 ",
        MCP_ALLOWED_ORIGINS=" http://localhost ",
        CACHE_ENABLED=False,
    )
    upstream = SimpleNamespace(
        close=AsyncMock(),
        ping=AsyncMock(return_value=PingResponse(status="success")),
        read_global_config=AsyncMock(
            return_value=SimpleNamespace(
                model_dump=lambda **kwargs: {"status": "success", "data": {}}
            )
        ),
        list_jobs=AsyncMock(
            return_value=SimpleNamespace(
                model_dump=lambda **kwargs: {"status": "success", "data": []}
            )
        ),
        list_bans=AsyncMock(
            return_value=SimpleNamespace(
                model_dump=lambda **kwargs: {"status": "success", "data": []}
            )
        ),
        list_instances=AsyncMock(
            return_value=SimpleNamespace(
                model_dump=lambda **kwargs: {"status": "success", "data": []}
            )
        ),
    )
    search_result = SearchResult(
        text="Configure BunkerWeb",
        title="Guide",
        url="https://docs.bunkerweb.io",
        category="guide",
        score=0.8754,
        chunk_id=1,
        doc_id="guide",
    )
    search = AsyncMock(return_value=[search_result])
    monkeypatch.setenv("SEARCH_MODE", "remote")
    monkeypatch.setattr(SearchClient, "search", search)
    monkeypatch.setattr("bunkerweb_mcp.main.get_settings", lambda: settings)
    for module in ("ban_handlers", "config_handlers", "instance_handlers"):
        monkeypatch.setattr(f"bunkerweb_mcp.tools.{module}.get_settings", lambda: settings)
    monkeypatch.setattr("bunkerweb_mcp.main.BunkerWebClient", lambda settings: upstream)
    app = create_app()
    headers = {
        "accept": "application/json, text/event-stream",
        "x-mcp-token": "test-token",
        "origin": "http://localhost",
        "mcp-protocol-version": "2025-11-25",
    }
    async with app.router.lifespan_context(app):
        assert app.state.fastmcp.session_manager._task_group is not None
        async with AsyncClient(
            transport=ASGITransport(app, raise_app_exceptions=False),
            base_url="http://localhost",
            headers=headers,
        ) as client:

            async def rpc(method, params=None):
                response = await client.post(
                    "/mcp/",
                    json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                )
                assert response.status_code == 200, response.text
                assert response.headers["content-type"].startswith("application/json")
                assert "mcp-session-id" not in response.headers
                return response.json()

            request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INITIALIZE}
            for token in ("", "wrong-token"):
                rejected = await client.post("/mcp/", json=request, headers={"x-mcp-token": token})
                assert rejected.status_code == 401
            invalid_host = await client.post(
                "/mcp/", json=request, headers={"host": "evil.example"}
            )
            assert invalid_host.status_code == 421
            invalid_origin = await client.post(
                "/mcp/", json=request, headers={"origin": "http://evil.example"}
            )
            assert invalid_origin.status_code == 403
            redirected = await client.post("/mcp", json=request)
            assert redirected.status_code == 307
            assert redirected.headers["location"] == "http://localhost/mcp/"
            assert (await client.post("/mcp/mcp", json=request)).status_code == 404
            initialized = await rpc("initialize", INITIALIZE)
            assert initialized["result"]["protocolVersion"] == "2025-11-25"
            notification = await client.post(
                "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
            assert notification.status_code == 202

            tools = (await rpc("tools/list"))["result"]["tools"]
            by_name = {tool["name"]: tool for tool in tools}
            assert "outputSchema" not in by_name["logs_read"]
            assert "outputSchema" in by_name["search_bunkerweb_docs"]
            called = (
                await rpc("tools/call", {"name": "logs_read", "arguments": {"source": "api.log"}})
            )["result"]
            assert not called["isError"]
            assert "structuredContent" not in called
            assert json.loads(called["content"][0]["text"])["lines"] == ["ready"]
            invalid = (await rpc("tools/call", {"name": "logs_read", "arguments": {}}))["result"]
            assert invalid["isError"]
            unknown = (
                await rpc(
                    "tools/call", {"name": "logs_read", "arguments": {"source": "unknown.log"}}
                )
            )["result"]
            assert unknown["isError"] and "Unknown log source" in str(unknown)

            prompts = (await rpc("prompts/list"))["result"]["prompts"]
            assert "logs_read" in {prompt["name"] for prompt in prompts}
            prompt = (await rpc("prompts/get", {"name": "logs_read"}))["result"]
            assert prompt["messages"][0]["role"] == "user"
            assert prompt["messages"][0]["content"]["text"]
            resources = (await rpc("resources/list"))["result"]["resources"]
            assert {r["uri"] for r in resources} == {
                "config://global",
                "logs://jobs",
                "bans://active",
                "instances://status",
            }
            for resource in resources:
                data = (await rpc("resources/read", {"uri": resource["uri"]}))["result"][
                    "contents"
                ][0]
                assert data["mimeType"] == "application/json"
                assert json.loads(data["text"])["status"] == "success"

            search_params = {"query": "configuration", "limit": 2}
            result = (
                await rpc(
                    "tools/call", {"name": "search_bunkerweb_docs", "arguments": search_params}
                )
            )["result"]
            expected = result["structuredContent"]
            assert expected["num_results"] == 1
            assert json.loads(result["content"][0]["text"]) == expected
            legacy_tools = (await client.get("/tools")).json()
            assert [t["name"] for t in legacy_tools].count("search_bunkerweb_docs") == 1
            legacy_result = await client.post(
                "/rpc", json={"id": 2, "tool": "search_bunkerweb_docs", "params": search_params}
            )
            assert legacy_result.status_code == 200
            assert legacy_result.json()["result"] == expected
            for error, visible in [
                (BunkerWebError("API unavailable"), True),
                (RuntimeError("private-detail"), False),
            ]:
                upstream.ping.side_effect = error
                failure = (await rpc("tools/call", {"name": "ping", "arguments": {}}))["result"]
                assert failure["isError"]
                assert (str(error) in str(failure)) is visible
                upstream.list_jobs.side_effect = error
                failure = await rpc("resources/read", {"uri": "logs://jobs"})
                assert "error" in failure
                assert (str(error) in str(failure)) is visible
            search.side_effect = RuntimeError("private-search-detail")
            failure = (
                await rpc(
                    "tools/call", {"name": "search_bunkerweb_docs", "arguments": search_params}
                )
            )["result"]
            assert failure["isError"] and "private-search-detail" not in str(failure)
            failure = await client.post(
                "/rpc", json={"tool": "search_bunkerweb_docs", "params": search_params}
            )
            assert failure.status_code == 500
            assert "private-search-detail" not in failure.text
    upstream.close.assert_awaited_once()
    assert app.state.fastmcp.session_manager._task_group is None


@pytest.mark.asyncio
async def test_stdio_initialize_list_call_and_shutdown(tmp_path):
    (tmp_path / "api.log").write_text("stdio ready\n")
    env = {
        **os.environ,
        "BUNKERWEB_LOGS_PATH": str(tmp_path),
        "SEARCH_MODE": "disabled",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "bunkerweb_mcp.cli",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:

        async def rpc(method, params=None):
            process.stdin.write(
                (
                    json.dumps(
                        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
                    )
                    + "\n"
                ).encode()
            )
            await process.stdin.drain()
            return json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=10))

        result = await rpc("initialize", INITIALIZE)
        assert result["result"]["protocolVersion"] == "2025-11-25"
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        tools = (await rpc("tools/list"))["result"]["tools"]
        assert "logs_read" in {tool["name"] for tool in tools}
        result = (
            await rpc("tools/call", {"name": "logs_read", "arguments": {"source": "api.log"}})
        )["result"]
        assert not result["isError"]
        assert "structuredContent" not in result
        assert json.loads(result["content"][0]["text"])["lines"] == ["stdio ready"]
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), timeout=10) == 0
        assert b"shutdown complete" in await process.stderr.read()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
