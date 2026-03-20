"""CLI entry point for stdio-based MCP server."""

import asyncio
import logging
import sys

from .client import BunkerWebClient
from .config import get_settings
from .mcp_adapter import create_fastmcp_server
from .prompt_catalog import load_catalog
from .tools import Tools
from .utils.logging import configure_logging

LOGGER = logging.getLogger(__name__)


async def run_stdio() -> None:
    """Run the FastMCP server in stdio mode for Claude Code integration."""
    settings = get_settings()
    configure_logging(settings.log_level)

    LOGGER.info("Starting BunkerWeb MCP server in stdio mode")
    LOGGER.info(f"Target API: {settings.bunkerweb_base_url}")

    client = BunkerWebClient(settings=settings)
    prompt_catalog = load_catalog(settings)
    tools = Tools(client, prompt_catalog=prompt_catalog)
    server = create_fastmcp_server(settings, tools)

    try:
        # Run the server in stdio mode
        await server.run_stdio_async()
    finally:
        await client.close()
        LOGGER.info("BunkerWeb MCP server shutdown complete")


def main() -> None:
    """Entry point for the CLI."""
    try:
        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        LOGGER.info("Received interrupt signal, shutting down")
        sys.exit(0)
    except Exception as exc:
        LOGGER.exception("Fatal error in MCP server", exc_info=exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
