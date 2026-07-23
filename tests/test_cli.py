"""Tests for CLI module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bunkerweb_mcp.cli import main, run_stdio


@pytest.mark.asyncio
async def test_run_stdio_initializes_components():
    """Test that run_stdio initializes all required components."""
    with (
        patch("bunkerweb_mcp.cli.get_settings") as mock_settings,
        patch("bunkerweb_mcp.cli.configure_logging") as mock_configure_logging,
        patch("bunkerweb_mcp.cli.BunkerWebClient") as mock_client_class,
        patch("bunkerweb_mcp.cli.load_catalog") as mock_load_catalog,
        patch("bunkerweb_mcp.cli.Tools") as mock_tools_class,
        patch("bunkerweb_mcp.cli.create_fastmcp_server") as mock_create_server,
    ):
        # Setup mocks
        mock_settings.return_value = MagicMock(
            log_level="INFO", bunkerweb_base_url="http://localhost:8888"
        )
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools
        mock_server = AsyncMock()
        mock_server.run_stdio_async = AsyncMock()
        mock_create_server.return_value = mock_server

        # Run the function
        await run_stdio()

        # Verify initialization sequence
        mock_settings.assert_called_once()
        mock_configure_logging.assert_called_once_with("INFO")
        mock_client_class.assert_called_once()
        mock_load_catalog.assert_called_once()
        mock_tools_class.assert_called_once()
        mock_create_server.assert_called_once()

        # Verify server runs in stdio mode
        mock_server.run_stdio_async.assert_awaited_once_with()

        # Verify client cleanup
        mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_stdio_cleans_up_on_exception():
    """Test that run_stdio cleans up resources even when exception occurs."""
    with (
        patch("bunkerweb_mcp.cli.get_settings") as mock_settings,
        patch("bunkerweb_mcp.cli.configure_logging"),
        patch("bunkerweb_mcp.cli.BunkerWebClient") as mock_client_class,
        patch("bunkerweb_mcp.cli.load_catalog"),
        patch("bunkerweb_mcp.cli.Tools"),
        patch("bunkerweb_mcp.cli.create_fastmcp_server") as mock_create_server,
    ):
        # Setup mocks
        mock_settings.return_value = MagicMock(
            log_level="INFO", bunkerweb_base_url="http://localhost:8888"
        )
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Make the stdio runner raise an exception
        mock_server = AsyncMock()
        mock_server.run_stdio_async = AsyncMock(side_effect=RuntimeError("Server failed"))
        mock_create_server.return_value = mock_server

        # Run and expect exception
        with pytest.raises(RuntimeError, match="Server failed"):
            await run_stdio()

        # Verify client was still closed
        mock_client.close.assert_called_once()


def test_main_runs_asyncio():
    """Test that main function runs the async run_stdio function."""
    with (
        patch("bunkerweb_mcp.cli.asyncio.run") as mock_asyncio_run,
        patch("bunkerweb_mcp.cli.run_stdio", new=MagicMock(return_value=None)),
    ):
        mock_asyncio_run.return_value = None

        main()

        # Verify asyncio.run was called with run_stdio
        mock_asyncio_run.assert_called_once()
        # The first argument should be the run_stdio coroutine
        args = mock_asyncio_run.call_args[0]
        assert len(args) == 1


def test_main_handles_keyboard_interrupt():
    """Test that main handles KeyboardInterrupt gracefully."""
    with (
        patch("bunkerweb_mcp.cli.asyncio.run") as mock_asyncio_run,
        patch("bunkerweb_mcp.cli.run_stdio", new=MagicMock(return_value=None)),
        patch("bunkerweb_mcp.cli.sys.exit") as mock_exit,
    ):
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        main()

        # Verify exit was called with 0
        mock_exit.assert_called_once_with(0)


def test_main_handles_general_exception():
    """Test that main handles general exceptions."""
    with (
        patch("bunkerweb_mcp.cli.asyncio.run") as mock_asyncio_run,
        patch("bunkerweb_mcp.cli.run_stdio", new=MagicMock(return_value=None)),
        patch("bunkerweb_mcp.cli.sys.exit") as mock_exit,
        patch("bunkerweb_mcp.cli.LOGGER") as mock_logger,
    ):
        test_exception = RuntimeError("Fatal error")
        mock_asyncio_run.side_effect = test_exception

        main()

        # Verify exception was logged
        mock_logger.exception.assert_called_once()

        # Verify exit was called with 1
        mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_run_stdio_logs_startup_info():
    """Test that run_stdio logs startup information."""
    with (
        patch("bunkerweb_mcp.cli.get_settings") as mock_settings,
        patch("bunkerweb_mcp.cli.configure_logging"),
        patch("bunkerweb_mcp.cli.BunkerWebClient") as mock_client_class,
        patch("bunkerweb_mcp.cli.load_catalog"),
        patch("bunkerweb_mcp.cli.Tools"),
        patch("bunkerweb_mcp.cli.create_fastmcp_server") as mock_create_server,
        patch("bunkerweb_mcp.cli.LOGGER") as mock_logger,
    ):
        # Setup mocks
        test_url = "http://test-server:9999"
        mock_settings.return_value = MagicMock(log_level="DEBUG", bunkerweb_base_url=test_url)
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_server = AsyncMock()
        mock_server.run_stdio_async = AsyncMock()
        mock_create_server.return_value = mock_server

        await run_stdio()

        # Verify startup logging
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Starting BunkerWeb MCP server" in msg for msg in info_calls)
        assert any(test_url in msg for msg in info_calls)
        assert any("shutdown complete" in msg for msg in info_calls)


@pytest.mark.asyncio
async def test_run_stdio_passes_settings_to_components():
    """Test that settings are correctly passed to all components."""
    with (
        patch("bunkerweb_mcp.cli.get_settings") as mock_settings,
        patch("bunkerweb_mcp.cli.configure_logging"),
        patch("bunkerweb_mcp.cli.BunkerWebClient") as mock_client_class,
        patch("bunkerweb_mcp.cli.load_catalog") as mock_load_catalog,
        patch("bunkerweb_mcp.cli.Tools") as mock_tools_class,
        patch("bunkerweb_mcp.cli.create_fastmcp_server") as mock_create_server,
    ):
        # Setup mocks with specific settings
        test_settings = MagicMock(
            log_level="DEBUG",
            bunkerweb_base_url="http://custom:7777",
            request_timeout_seconds=60.0,
        )
        mock_settings.return_value = test_settings

        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools
        mock_server = AsyncMock()
        mock_server.run_stdio_async = AsyncMock()
        mock_create_server.return_value = mock_server

        await run_stdio()

        # Verify settings object was passed to components
        mock_client_class.assert_called_once_with(settings=test_settings)
        mock_load_catalog.assert_called_once_with(test_settings)
        mock_tools_class.assert_called_once_with(mock_client, prompt_catalog=mock_catalog)
        mock_create_server.assert_called_once_with(test_settings, mock_tools)
