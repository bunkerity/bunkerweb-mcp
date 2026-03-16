"""Bridge between legacy tools registry and the official MCP server."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import Message, Prompt
from mcp.server.fastmcp.resources import FunctionResource
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyUrl, BaseModel
from pydantic.fields import PydanticUndefined  # type: ignore[attr-defined]

from .config import Settings
from .tools import Tools

ToolHandler = Callable[[BaseModel], Awaitable[dict[str, Any]]]


def _build_tool_callable(
    *,
    name: str,
    params_model: type[BaseModel],
    description: str,
    handler: ToolHandler,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a FastMCP-compatible callable wrapping a legacy tool handler."""

    async def tool_callable(**raw_kwargs: Any) -> dict[str, Any]:
        params = params_model.model_validate(raw_kwargs)
        return await handler(params)

    parameters: list[inspect.Parameter] = []
    for field_name, field_info in params_model.model_fields.items():
        default = inspect._empty if field_info.is_required() else field_info.default
        parameters.append(
            inspect.Parameter(
                field_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default if default is not PydanticUndefined else inspect._empty,
                annotation=field_info.annotation or Any,
            )
        )

    tool_callable.__name__ = f"{name}_tool"
    tool_callable.__doc__ = description
    # Synthesize an annotated signature so FastMCP can emit accurate JSON schema.
    tool_callable.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])  # type: ignore[attr-defined]
    return tool_callable


def _build_prompt_callable(name: str, prompt_text: str) -> Callable[[], Awaitable[list[Message]]]:
    async def prompt_callable() -> list[Message]:
        return [Message(role="user", content=prompt_text)]

    prompt_callable.__name__ = f"{name}_prompt"
    prompt_callable.__doc__ = f"Guidance prompt for the '{name}' tool."
    return prompt_callable


def create_fastmcp_server(settings: Settings, tools: Tools) -> FastMCP:
    """Instantiate and populate a FastMCP server instance."""

    # Configure transport security from settings
    # Parse comma-separated lists of allowed hosts and origins
    allowed_hosts = [h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()]
    allowed_origins = [o.strip() for o in settings.mcp_allowed_origins.split(",") if o.strip()]

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.mcp_enable_dns_rebinding_protection,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

    server = FastMCP(
        name="BunkerWeb MCP Server",
        instructions=(
            "Manage BunkerWeb resources through the official MCP server. "
            f"Target API base: {settings.bunkerweb_base_url}."
        ),
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
        transport_security=transport_security,
    )

    # Register all tools from the tools registry
    for name, params_model, handler, description, prompt_text in tools.iter_registered():
        tool_fn = _build_tool_callable(
            name=name,
            params_model=params_model,
            description=description,
            handler=handler,
        )
        server.add_tool(tool_fn, name=name, description=description, structured_output=False)
        if prompt_text:
            prompt_fn = _build_prompt_callable(name, prompt_text)
            server.add_prompt(
                Prompt.from_function(
                    prompt_fn,
                    name=name,
                    description=f"Suggested context for the '{name}' tool.",
                )
            )

    # Register MCP resources for read-only data access
    _register_resources(server, tools)

    # Register semantic search tool
    _register_search_tool(server)

    return server


def _register_resources(server: FastMCP, tools: Tools) -> None:
    """Register MCP resources that expose BunkerWeb data."""

    # Resource: Global configuration
    async def get_global_config() -> str:
        """Fetch the current global BunkerWeb configuration."""
        tool = tools.get_tool("global_config_read")
        if tool is None:
            return json.dumps({"error": "global_config_read tool not available"})
        try:
            result = await tool({"full": True, "methods": False})

            # Check if the API returned empty data
            if result.get("status") == "success" and not result.get("data"):
                return json.dumps(
                    {
                        "status": "success",
                        "message": (
                            "The BunkerWeb API /global_settings endpoint returned no configuration data. "
                            "This is a known limitation of the BunkerWeb API. "
                            "To view service-specific configuration (which includes global settings), "
                            "use the 'get_service' tool with full=true instead."
                        ),
                        "data": None,
                    },
                    indent=2,
                )

            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    server.add_resource(
        FunctionResource(
            uri=AnyUrl("config://global"),
            name="Global Configuration",
            description="Current BunkerWeb global configuration with all settings",
            fn=get_global_config,
            mime_type="application/json",
        )
    )

    # Resource: Scheduler jobs and execution history
    async def get_jobs_history() -> str:
        """Fetch scheduler jobs with their execution history."""
        tool = tools.get_tool("jobs_list")
        if tool is None:
            return json.dumps({"error": "jobs_list tool not available"})
        try:
            result = await tool({})
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    server.add_resource(
        FunctionResource(
            uri=AnyUrl("logs://jobs"),
            name="Job Execution History",
            description="Scheduler jobs with their execution history and status",
            fn=get_jobs_history,
            mime_type="application/json",
        )
    )

    # Resource: Active bans list
    async def get_active_bans() -> str:
        """Fetch currently active IP bans."""
        tool = tools.get_tool("list_bans")
        if tool is None:
            return json.dumps({"error": "list_bans tool not available"})
        try:
            result = await tool({})
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    server.add_resource(
        FunctionResource(
            uri=AnyUrl("bans://active"),
            name="Active IP Bans",
            description="List of currently active IP bans with expiry and reason",
            fn=get_active_bans,
            mime_type="application/json",
        )
    )

    # Resource: Instance status
    async def get_instances_status() -> str:
        """Fetch status of all BunkerWeb instances."""
        tool = tools.get_tool("list_instances")
        if tool is None:
            return json.dumps({"error": "list_instances tool not available"})
        try:
            result = await tool({})
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    server.add_resource(
        FunctionResource(
            uri=AnyUrl("instances://status"),
            name="Instance Status",
            description="Current status and health of all registered BunkerWeb instances",
            fn=get_instances_status,
            mime_type="application/json",
        )
    )


def _register_search_tool(server: FastMCP) -> None:
    """Register the semantic search tool for BunkerWeb documentation."""
    import logging

    logger = logging.getLogger(__name__)

    # Initialize lightweight search client
    try:
        from .search_client import SearchClient

        # Create client from environment variables
        search_client = SearchClient.from_env()

        if not search_client.enabled:
            logger.info("Search is disabled (SEARCH_MODE=disabled)")
            return

        logger.info(f"Search client initialized (API URL: {search_client.api_url})")

    except Exception as e:
        logger.error(f"Failed to initialize search client: {e}")
        logger.exception("Search tool initialization error")
        return

    async def search_bunkerweb_docs(
        query: str,
        limit: int = 5,
        category: str | None = None,
        min_score: float = 0.2,
        max_content_length: int = 500,
    ) -> dict[str, Any]:
        """
        Search the BunkerWeb documentation using semantic search.

        This tool uses AI-powered semantic search to find relevant documentation
        based on the meaning of your query, not just keywords. It understands
        synonyms, context, and can work in multiple languages.

        Args:
            query: Your search query (e.g., "how to configure ModSecurity",
                   "block malicious bots", "SSL certificate setup")
            limit: Maximum number of results to return (default: 5)
            category: Optional category filter (e.g., "api", "plugins", "features")
            min_score: Minimum relevance score (0-1). Results below this threshold
                      are excluded. Default: 0.2 (low-moderate relevance)
            max_content_length: Maximum characters of content to return per result.
                               Use 0 for full content. Default: 500

        Returns:
            Search results with relevant documentation sections, automatically
            deduplicated to show only one result per document.

        Examples:
            - "ModSecurity configuration" → finds WAF/CRS documentation
            - "block bots" → finds antibot docs
            - "API usage" → finds API documentation

        Note:
            Results are automatically deduplicated to avoid showing multiple
            chunks from the same document. Only the most relevant chunk per
            document is returned.
        """
        try:
            # Use async context manager to ensure proper cleanup
            async with search_client:
                results = await search_client.search(
                    query=query,
                    limit=limit,
                    category=category,
                    min_score=min_score,
                    max_content_length=max_content_length,
                )

            # Format results for Claude
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        "title": result.title,
                        "url": result.url,
                        "category": result.category,
                        "relevance_score": round(result.score, 3),
                        "content": result.text,
                        "doc_id": result.doc_id,
                    }
                )

            return {
                "status": "success",
                "query": query,
                "num_results": len(formatted_results),
                "results": formatted_results,
            }

        except Exception as exc:
            logger.exception("Search API error")
            return {
                "status": "error",
                "error": str(exc),
                "query": query,
            }

    # Register the tool
    server.add_tool(
        search_bunkerweb_docs,
        name="search_bunkerweb_docs",
        description="Semantic search across BunkerWeb documentation using AI embeddings (via remote API)",
    )

    logger.info("Registered search_bunkerweb_docs tool (remote mode)")
