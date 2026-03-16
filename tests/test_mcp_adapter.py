"""Tests for MCP adapter module."""

from unittest.mock import MagicMock, patch

import pytest

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.mcp_adapter import (
    _build_prompt_callable,
    _build_tool_callable,
    create_fastmcp_server,
)


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

    with patch("bunkerweb_mcp.mcp_adapter.FastMCP") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # Verify FastMCP was initialized with correct parameters
        mock_fastmcp.assert_called_once()
        call_kwargs = mock_fastmcp.call_args.kwargs

        assert call_kwargs["name"] == "BunkerWeb MCP Server"
        assert "http://test-server:8888" in call_kwargs["instructions"]
        assert call_kwargs["json_response"] is True
        assert call_kwargs["stateless_http"] is True
        assert call_kwargs["streamable_http_path"] == "/"


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

    with patch("bunkerweb_mcp.mcp_adapter.FastMCP") as mock_fastmcp:
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

    with patch("bunkerweb_mcp.mcp_adapter.FastMCP") as mock_fastmcp:
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

    with patch("bunkerweb_mcp.mcp_adapter.FastMCP") as mock_fastmcp:
        mock_server = MagicMock()
        mock_fastmcp.return_value = mock_server

        create_fastmcp_server(settings, tools)

        # Check that add_resource was called 4 times (one for each resource)
        assert mock_server.add_resource.call_count == 4

        # Get the URIs of all registered resources
        resource_uris = set()
        for call in mock_server.add_resource.call_args_list:
            resource = call[0][0]
            if hasattr(resource, "uri"):
                resource_uris.add(str(resource.uri))

        # Verify all expected resources were registered
        expected_uris = {
            "config://global",
            "logs://jobs",
            "bans://active",
            "instances://status",
        }
        assert resource_uris == expected_uris
