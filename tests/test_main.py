import json
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from asgi import WebSocketSession
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from bunkerweb_mcp.exceptions import ToolExecutionError, ToolValidationError
from bunkerweb_mcp.main import create_app


class StubSettings(SimpleNamespace):
    log_level: str = "INFO"
    websocket_token: str | None = "secret"
    bunkerweb_base_url: str = "http://testserver"
    bunkerweb_api_token: str | None = None
    request_timeout_seconds: float = 1.0
    max_retries: int = 1
    retry_backoff_initial: float = 0.1
    retry_backoff_max: float = 0.1
    rate_limit_enabled: bool = False

    def get_websocket_token(self) -> str | None:
        """Get WebSocket token value for testing."""
        return self.websocket_token

    def get_api_token(self) -> str | None:
        """Get API token value for testing."""
        return self.bunkerweb_api_token

    rate_limit_tools: str = "30/minute"
    rate_limit_rpc: str = "100/minute"
    rate_limit_ws: str = "500/minute"
    cache_enabled: bool = False


class StubParamsModel:
    """Stub params model for testing."""

    @staticmethod
    def model_json_schema():
        return {}


class StubTools:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.client: StubClient | None = None
        self.prompts: dict[str, str] = {}

    def list_descriptors(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": "",
                "input_schema": {},
                **({"prompt": self.prompts[name]} if name in self.prompts else {}),
            }
            for name in sorted(self.handlers)
        ]

    def iter_registered(self):
        """Yield metadata for each registered tool."""
        for name in sorted(self.handlers):
            handler = self.handlers[name]
            description = ""
            prompt_text = self.prompts.get(name)
            yield name, StubParamsModel, handler, description, prompt_text

    def get_tool(self, name: str) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None:
        handler = self.handlers.get(name)
        if handler is None:
            return None

        async def wrapper(params: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((name, params))
            return await handler(params)

        return wrapper

    def get_prompt(self, name: str) -> str | None:
        return self.prompts.get(name)


class StubClient:
    def __init__(self, settings: StubSettings) -> None:
        self.settings = settings
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class StubFastMCP:
    """Stub FastMCP server for testing."""

    def streamable_http_app(self):
        """Return a stub ASGI app."""
        from fastapi import FastAPI

        stub_app = FastAPI()
        return stub_app


class StubPromptCatalog:
    """Stub prompt catalog for testing."""

    def __init__(self, prompts=None):
        self._prompts = prompts or {}

    def get(self, name: str):
        return self._prompts.get(name)

    def descriptors(self):
        return self._prompts


@pytest.fixture
def app_fixture(monkeypatch: pytest.MonkeyPatch):
    tools = StubTools()
    settings = StubSettings()

    monkeypatch.setattr("bunkerweb_mcp.main.get_settings", lambda: settings)
    monkeypatch.setattr("bunkerweb_mcp.main.BunkerWebClient", lambda settings: StubClient(settings))
    monkeypatch.setattr("bunkerweb_mcp.main.load_catalog", lambda settings: StubPromptCatalog())

    def tools_factory(client: StubClient, prompt_catalog=None) -> StubTools:
        tools.client = client
        if prompt_catalog is not None:
            tools.prompts = prompt_catalog.descriptors()
        return tools

    monkeypatch.setattr("bunkerweb_mcp.main.Tools", tools_factory)

    # Mock the FastMCP server creation
    def stub_create_fastmcp_server(settings, tools):
        return StubFastMCP()

    monkeypatch.setattr("bunkerweb_mcp.main.create_fastmcp_server", stub_create_fastmcp_server)

    app = create_app()
    return app, tools, settings


@pytest_asyncio.fixture
async def async_client(app_fixture):
    app, tools, settings = app_fixture
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, tools, settings


@pytest.mark.asyncio
async def test_list_tools_returns_descriptors(async_client) -> None:
    client, tools, _ = async_client

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success"}

    tools.handlers["ping"] = handler

    response = await client.get("/tools")

    assert response.status_code == 200
    expected_descriptor = {"name": "ping", "description": "", "input_schema": {}}
    if "ping" in tools.prompts:
        expected_descriptor["prompt"] = tools.prompts["ping"]
    assert response.json() == [expected_descriptor]


@pytest.mark.asyncio
async def test_rpc_invokes_tool(async_client) -> None:
    client, tools, _ = async_client

    async def echo_handler(params: dict[str, Any]) -> dict[str, Any]:
        return {"echo": params}

    tools.handlers["echo"] = echo_handler

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "secret"},
        json={"id": "req-1", "tool": "echo", "params": {"value": 1}},
    )

    assert response.status_code == 200
    expected_response = {"id": "req-1", "result": {"echo": {"value": 1}}}
    prompt_value = tools.get_prompt("echo")
    if prompt_value:
        expected_response["prompt"] = prompt_value
    assert response.json() == expected_response
    assert tools.calls == [("echo", {"value": 1})]


@pytest.mark.asyncio
async def test_rpc_missing_tool_field(async_client) -> None:
    client, _, _ = async_client

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "secret"},
        json={"id": "req-1"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing 'tool' field"


@pytest.mark.asyncio
async def test_rpc_unknown_tool(async_client) -> None:
    client, tools, _ = async_client
    tools.handlers.clear()

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "secret"},
        json={"id": "req-1", "tool": "unknown", "params": {}},
    )

    assert response.status_code == 404
    assert "Unknown tool" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rpc_validation_error(async_client) -> None:
    client, tools, _ = async_client

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
        raise ToolValidationError("invalid")

    tools.handlers["validate"] = handler

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "secret"},
        json={"id": "req-1", "tool": "validate", "params": {}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid"


@pytest.mark.asyncio
async def test_rpc_execution_error(async_client) -> None:
    client, tools, _ = async_client

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
        raise ToolExecutionError("boom")

    tools.handlers["fail"] = handler

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "secret"},
        json={"id": "req-1", "tool": "fail", "params": {}},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "boom"


@pytest.mark.asyncio
async def test_rpc_token_mismatch(async_client) -> None:
    client, tools, settings = async_client

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success"}

    tools.handlers["echo"] = handler
    settings.websocket_token = "secret"

    response = await client.post(
        "/rpc",
        headers={"x-mcp-token": "wrong"},
        json={"id": "req-1", "tool": "echo", "params": {}},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MCP token"


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_token(app_fixture) -> None:
    app, tools, settings = app_fixture
    settings.websocket_token = "secret"

    async def handler(_: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}

    tools.handlers["echo"] = handler

    async with WebSocketSession(app, "/ws?token=wrong") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            await ws.receive_text()
        assert exc.value.code == 1008


@pytest.mark.asyncio
async def test_websocket_executes_tool(app_fixture) -> None:
    app, tools, settings = app_fixture
    settings.websocket_token = "secret"

    async def handler(params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": params.get("value")}

    tools.handlers["echo"] = handler

    async with WebSocketSession(app, "/ws?token=secret") as ws:
        await ws.send_text(json.dumps({"id": "req-1", "tool": "echo", "params": {"value": 42}}))
        message = json.loads(await ws.receive_text())
        assert message == {"id": "req-1", "result": {"ok": 42}}


@pytest.mark.asyncio
async def test_websocket_handles_unknown_tool(app_fixture) -> None:
    app, tools, settings = app_fixture
    settings.websocket_token = None
    tools.handlers.clear()

    async with WebSocketSession(app, "/ws") as ws:
        await ws.send_text(json.dumps({"id": "req-1", "tool": "missing", "params": {}}))
        message = json.loads(await ws.receive_text())
        assert message["error"]["code"] == "unknown_tool"
