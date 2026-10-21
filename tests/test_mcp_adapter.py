"""Tests for MCP adapter module."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.mcp_adapter import (
    _build_prompt_callable,
    _build_tool_callable,
    create_fastmcp_server,
)
from bunkerweb_mcp.prompt_catalog import PromptCatalog
from bunkerweb_mcp.search_client import SearchClient
from bunkerweb_mcp.skill_catalog import SKILL_URI_PREFIX, load_skills
from bunkerweb_mcp.tools import Tools
from bunkerweb_mcp.tools.registry import effect_for


@pytest.mark.asyncio
async def test_read_only_server_registers_no_write_tools_or_prompts() -> None:
    settings = Settings(SEARCH_MODE="remote", MCP_ENABLE_SKILLS=False)
    catalog = PromptCatalog(
        {
            "get_service": "Read a service",
            "update_service": "Write a service",
            "authenticate": "Auth",
        }
    )
    tools = Tools(SimpleNamespace(), prompt_catalog=catalog, read_only=True)  # type: ignore[arg-type]
    server = create_fastmcp_server(settings, tools)
    registered = await server.list_tools()
    names = {tool.name for tool in registered}
    assert "get_service" in names
    assert "search_bunkerweb_docs" in names
    assert "update_service" not in names
    assert "authenticate" not in names
    assert all(effect_for(name).read_only for name in names)
    assert {prompt.name for prompt in await server.list_prompts()} == {"get_service"}


@pytest.mark.asyncio
async def test_registered_tools_carry_annotations() -> None:
    settings = Settings(bunkerweb_base_url="http://test:8888", SEARCH_MODE="remote")
    server = create_fastmcp_server(settings, Tools(SimpleNamespace()))  # type: ignore[arg-type]
    by_name = {tool.name: tool for tool in await server.list_tools()}

    assert by_name["get_service"].annotations.read_only_hint is True
    assert by_name["create_service"].annotations.read_only_hint is False
    assert by_name["create_service"].annotations.destructive_hint is False
    for name in ("update_service", "config_create", "configs_upload"):
        assert by_name[name].annotations.destructive_hint is True
    assert by_name["search_bunkerweb_docs"].annotations.read_only_hint is True
    assert all(tool.annotations.idempotent_hint is None for tool in by_name.values())


class StubFieldInfo:
    """Stub field info for Pydantic models."""

    def __init__(self, default=None, required=True, annotation=None):
        self.default = default
        self._required = required
        self.annotation = annotation or str

    def is_required(self):
        return self._required


class StubParamsModel:
    """Stub params model for testing."""

    model_fields = {}  # Class attribute, not method

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)


class StubTools:
    """Stub Tools class for testing."""

    def __init__(self):
        self.tool_handlers = {}

    def iter_registered(self):
        """Yield stub tool metadata."""
        for name, handler in self.tool_handlers.items():
            yield name, StubParamsModel, handler, f"Description for {name}", f"Prompt for {name}"

    def get_tool(self, name: str):
        """Get a tool handler by name."""
        handler = self.tool_handlers.get(name)
        if handler is None:
            return None

        # Wrap the handler to match the expected signature
        async def tool_wrapper(params):
            return await handler(params)

        return tool_wrapper


@pytest.mark.asyncio
async def test_build_tool_callable_executes_handler():
    """Test that built tool callable executes the handler correctly."""
    handler_called = False
    handler_params = None

    async def test_handler(params):
        nonlocal handler_called, handler_params
        handler_called = True
        handler_params = params
        return {"result": "success"}

    tool_callable = _build_tool_callable(
        name="test_tool",
        params_model=StubParamsModel,
        description="Test tool",
        handler=test_handler,
    )

    # Execute the tool
    result = await tool_callable()

    assert handler_called
    assert result == {"result": "success"}
    assert tool_callable.__name__ == "test_tool_tool"
    assert tool_callable.__doc__ == "Test tool"


@pytest.mark.asyncio
async def test_build_tool_callable_validates_params():
    """Test that tool callable validates parameters."""

    async def test_handler(params):
        return {"value": params.value if hasattr(params, "value") else None}

    tool_callable = _build_tool_callable(
        name="echo_tool",
        params_model=StubParamsModel,
        description="Echo tool",
        handler=test_handler,
    )

    result = await tool_callable(value=42)
    assert result["value"] == 42


@pytest.mark.asyncio
async def test_build_prompt_callable_returns_message():
    """Test that prompt callable returns properly formatted message."""
    prompt_text = "This is a test prompt for the tool."

    prompt_callable = _build_prompt_callable("test_tool", prompt_text)

    messages = await prompt_callable()

    assert len(messages) == 1
    assert messages[0].role == "user"
    # Content is a TextContent object with a text attribute
    assert messages[0].content.text == prompt_text
    assert prompt_callable.__name__ == "test_tool_prompt"
    assert "test_tool" in prompt_callable.__doc__


def test_create_fastmcp_server_initializes():
    """Test that FastMCP server is created with correct configuration."""
    settings = Settings(
        bunkerweb_base_url="http://test-server:8888",
        log_level="INFO",
    )

    tools = StubTools()

    # Add a test tool
    async def test_handler(params):
        return {"status": "ok"}

    tools.tool_handlers["ping"] = test_handler

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # Verify FastMCP was initialized with correct parameters
        mock_fastmcp.assert_called_once()
        call_kwargs = mock_fastmcp.call_args.kwargs

        assert call_kwargs["name"] == "BunkerWeb MCP Server"
        assert "http://test-server:8888" in call_kwargs["instructions"]
        assert "json_response" not in call_kwargs
        assert "stateless_http" not in call_kwargs
        assert "streamable_http_path" not in call_kwargs


def test_create_fastmcp_server_registers_tools():
    """Test that all tools are registered with the FastMCP server."""
    settings = Settings(bunkerweb_base_url="http://test:8888")
    tools = StubTools()

    # Add multiple test tools
    async def ping_handler(params):
        return {"status": "ok"}

    async def health_handler(params):
        return {"healthy": True}

    tools.tool_handlers["ping"] = ping_handler
    tools.tool_handlers["health"] = health_handler

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # Verify add_tool was called for each tool (2 from StubTools)
        # Note: search tool is not registered if faiss is not available
        assert mock_server.add_tool.call_count >= 2


def test_create_fastmcp_server_registers_prompts():
    """Test that prompts are registered for tools."""
    settings = Settings(bunkerweb_base_url="http://test:8888")
    tools = StubTools()

    async def test_handler(params):
        return {"result": "ok"}

    tools.tool_handlers["test_tool"] = test_handler

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # Verify add_prompt was called (since iter_registered returns prompts)
        assert mock_server.add_prompt.call_count == 1


@pytest.mark.asyncio
async def test_resources_are_registered():
    """Test that all 4 resources are registered with the FastMCP server."""
    settings = Settings(bunkerweb_base_url="http://test:8888")
    tools = StubTools()

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # 4 data resources plus one per bundled skill file
        assert mock_server.add_resource.call_count == 4 + sum(
            len(skill.files) for skill in load_skills()
        )

        resource_uris = {str(c[0][0].uri) for c in mock_server.add_resource.call_args_list}
        assert {u for u in resource_uris if not u.startswith("skill://")} == {
            "config://global",
            "logs://jobs",
            "bans://active",
            "instances://status",
        }
        assert "skill://bunkerweb/bunkerweb/SKILL.md" in resource_uris


def test_skill_resource_names_are_paths_relative_to_the_skill():
    """The skill name in the URI authority must not leak into reference-file names."""
    settings = Settings(bunkerweb_base_url="http://test:8888")

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, StubTools())

        names = {
            str(c[0][0].uri): c[0][0].name
            for c in mock_server.add_resource.call_args_list
            if str(c[0][0].uri).startswith("skill://")
        }

    for skill in load_skills():
        for file in skill.files:
            prefix = f"{SKILL_URI_PREFIX}/{skill.name}/"
            expected = skill.name if file.uri == skill.uri else file.uri.removeprefix(prefix)
            assert names[file.uri] == expected
    assert (
        names["skill://bunkerweb/bunkerweb/references/all-in-one.md"] == "references/all-in-one.md"
    )


def test_skills_disabled_registers_nothing():
    """MCP_ENABLE_SKILLS=false keeps skill:// URIs and the instructions sentence out."""
    settings = Settings(bunkerweb_base_url="http://test:8888", MCP_ENABLE_SKILLS=False)

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, StubTools())

        uris = [str(c[0][0].uri) for c in mock_server.add_resource.call_args_list]
        assert len(uris) == 4
        assert not any(u.startswith("skill://") for u in uris)
        assert "Agent Skills" not in mock_fastmcp.call_args.kwargs["instructions"]


def test_skills_enabled_adds_instructions_sentence():
    settings = Settings(bunkerweb_base_url="http://test:8888")

    with patch("bunkerweb_mcp.mcp_adapter.MCPServer") as mock_fastmcp:
        mock_fastmcp.return_value = MagicMock()

        create_fastmcp_server(settings, StubTools())

        assert (
            "BunkerWeb Agent Skills are served as resources under skill://bunkerweb/; "
            "start with skill://bunkerweb/bunkerweb/SKILL.md."
        ) in mock_fastmcp.call_args.kwargs["instructions"]


def test_search_client_from_settings():
    settings = Settings(SEARCH_MODE="remote", SEARCH_API_URL="http://x", SEARCH_TIMEOUT=3.5)

    client = SearchClient.from_settings(settings)

    assert (client.enabled, client.api_url, client.timeout) == (True, "http://x", 3.5)


def test_search_client_from_settings_disabled():
    client = SearchClient.from_settings(Settings(SEARCH_MODE="disabled"))

    assert client.enabled is False
