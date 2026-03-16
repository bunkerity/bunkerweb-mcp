"""FastAPI application exposing MCP-compatible endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .client import BunkerWebClient
from .config import get_settings
from .exceptions import ToolExecutionError, ToolValidationError
from .mcp_adapter import create_fastmcp_server
from .metrics import (
    active_websockets,
    initialize_metrics,
    tool_calls_total,
    tool_duration_seconds,
)
from .prompt_catalog import load_catalog
from .rate_limiter import WebSocketRateLimiter
from .tools import Tools
from .tracing import setup_tracing
from .utils.logging import configure_logging

LOGGER = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    client = BunkerWebClient(settings=settings)
    prompt_catalog = load_catalog(settings)
    tools = Tools(client, prompt_catalog=prompt_catalog)
    fastmcp_server = create_fastmcp_server(settings, tools)

    # Initialize WebSocket rate limiter (500 messages per minute)
    ws_rate_limiter = WebSocketRateLimiter(max_messages=500, window_seconds=60)

    # Create the streamable HTTP app first to initialize the session manager
    mcp_app = fastmcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        # Initialize the FastMCP server's task group for streamable HTTP
        async with fastmcp_server.session_manager.run():
            try:
                yield
            finally:
                await client.close()

    app = FastAPI(title="BunkerWeb MCP Server", version="0.1.0", lifespan=lifespan)
    app.mount("/mcp", mcp_app)
    app.state.fastmcp = fastmcp_server
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Initialize metrics
    initialize_metrics(version="0.1.0")

    # Initialize tracing
    setup_tracing(app, service_name="mcp-bunkerweb")

    async def get_tools() -> Tools:
        return tools

    async def get_mcp_token() -> str | None:
        return settings.get_websocket_token()

    def _check_token(provided: str | None, expected: str | None) -> None:
        if expected and provided != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MCP token"
            )

    @app.get("/tools")
    async def list_tools(
        request: Request, tools: Tools = Depends(get_tools)
    ) -> list[dict[str, Any]]:
        if settings.rate_limit_enabled:
            await limiter.check_request_limit(  # type: ignore[attr-defined]
                request, settings.rate_limit_tools, get_remote_address(request)
            )

        # Get BunkerWeb API tools
        tool_list = tools.list_descriptors()

        # Add FastMCP tools (like search_bunkerweb_docs) if available
        # FastMCP tools are registered in fastmcp_server but not in the Tools object
        fastmcp_server = request.app.state.fastmcp
        if hasattr(fastmcp_server, "_tool_manager"):
            fastmcp_tools = fastmcp_server._tool_manager.list_tools()
            for tool in fastmcp_tools:
                tool_name = tool.name
                # Skip if already in the list (avoid duplicates)
                if not any(t.get("name") == tool_name for t in tool_list):
                    tool_list.append(
                        {
                            "name": tool_name,
                            "description": tool.description or "",
                            "input_schema": tool.parameters
                            if isinstance(tool.parameters, dict)
                            else {},
                        }
                    )

        return tool_list

    @app.post("/rpc")
    async def rpc_endpoint(
        request: Request,
        tools: Tools = Depends(get_tools),
        expected_token: str | None = Depends(get_mcp_token),
    ) -> JSONResponse:
        if settings.rate_limit_enabled:
            await limiter.check_request_limit(  # type: ignore[attr-defined]
                request, settings.rate_limit_rpc, get_remote_address(request)
            )

        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - FastAPI pre-validates
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
            ) from exc

        provided_token = request.headers.get("x-mcp-token")
        _check_token(provided_token, expected_token)

        tool_name = payload.get("tool")
        params = payload.get("params", {})
        request_id = payload.get("id")

        if not tool_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'tool' field"
            )

        # Try to get handler from BunkerWeb API tools first
        handler = tools.get_tool(tool_name)
        prompt_text = tools.get_prompt(tool_name) if handler else None
        is_async_handler = True  # BunkerWeb tools are async
        is_fastmcp_tool = False

        # If not found, try FastMCP tools (like search_bunkerweb_docs)
        if handler is None:
            fastmcp_server = request.app.state.fastmcp
            if hasattr(fastmcp_server, "_tool_manager"):
                fastmcp_tool = fastmcp_server._tool_manager.get_tool(tool_name)
                if fastmcp_tool is not None:
                    handler = fastmcp_tool.fn
                    is_async_handler = fastmcp_tool.is_async
                    is_fastmcp_tool = True
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool '{tool_name}'"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool '{tool_name}'"
                )

        try:
            start = time.monotonic()
            # FastMCP tools expect **kwargs, BunkerWeb tools expect a dict
            if is_fastmcp_tool:
                if is_async_handler:
                    result = await handler(**params)  # type: ignore[call-arg]
                else:
                    result = handler(**params)  # type: ignore[call-arg]
            else:
                result = await handler(params)
            duration = time.monotonic() - start

            # Record metrics
            tool_calls_total.labels(tool_name=tool_name, status="success").inc()
            tool_duration_seconds.labels(tool_name=tool_name).observe(duration)

            LOGGER.info(
                "tool_call", extra={"metrics": {"tool": tool_name, "duration_seconds": duration}}
            )
        except ToolValidationError as exc:
            tool_calls_total.labels(tool_name=tool_name, status="validation_error").inc()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ToolExecutionError as exc:
            tool_calls_total.labels(tool_name=tool_name, status="execution_error").inc()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        response_payload: dict[str, Any] = {"id": request_id, "result": result}
        if prompt_text:
            response_payload["prompt"] = prompt_text

        return JSONResponse(response_payload)

    @app.websocket("/ws")
    async def websocket_endpoint(
        ws: WebSocket,
        tools: Tools = Depends(get_tools),
        expected_token: str | None = Depends(get_mcp_token),
    ) -> None:
        await ws.accept()
        active_websockets.inc()
        token = ws.query_params.get("token")
        connection_id = f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"

        try:
            if expected_token and token != expected_token:
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            while True:
                raw = await ws.receive_text()

                # Check rate limit if enabled
                if settings.rate_limit_enabled and ws_rate_limiter.check_rate_limit(connection_id):
                    await ws.send_text(
                        json.dumps(
                            {
                                "error": {
                                    "code": "rate_limit_exceeded",
                                    "message": f"Rate limit exceeded: max {ws_rate_limiter.max_messages} messages per {ws_rate_limiter.window_seconds}s",
                                }
                            }
                        )
                    )
                    continue

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(
                        json.dumps({"error": {"code": "invalid_json", "message": "Invalid JSON"}})
                    )
                    continue

                request_id = message.get("id")
                tool_name = message.get("tool")
                params = message.get("params", {})

                if not tool_name:
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {
                                    "code": "missing_tool",
                                    "message": "Missing 'tool' field",
                                },
                            }
                        )
                    )
                    continue

                handler = tools.get_tool(tool_name)
                if handler is None:
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {
                                    "code": "unknown_tool",
                                    "message": f"Unknown tool '{tool_name}'",
                                },
                            }
                        )
                    )
                    continue
                prompt_text = tools.get_prompt(tool_name)

                try:
                    result = await asyncio.wait_for(handler(params), timeout=25.0)
                    message_payload = {"id": request_id, "result": result}
                    if prompt_text:
                        message_payload["prompt"] = prompt_text
                    await ws.send_text(json.dumps(message_payload))
                except TimeoutError:
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {
                                    "code": "timeout",
                                    "message": "Tool execution exceeded 25s",
                                },
                            }
                        )
                    )
                except ToolValidationError as exc:
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {"code": "validation_error", "message": str(exc)},
                            }
                        )
                    )
                except ToolExecutionError as exc:
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {"code": "execution_error", "message": str(exc)},
                            }
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Unhandled tool error", extra={"tool": tool_name})
                    await ws.send_text(
                        json.dumps(
                            {
                                "id": request_id,
                                "error": {"code": "internal_error", "message": str(exc)},
                            }
                        )
                    )
        except WebSocketDisconnect:
            return
        finally:
            # Cleanup rate limiter tracking data on disconnect
            active_websockets.dec()
            if settings.rate_limit_enabled:
                ws_rate_limiter.cleanup_connection(connection_id)

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus metrics endpoint.

        Returns:
            Prometheus-formatted metrics data
        """
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness probe - is the server running?

        Returns:
            Health status with timestamp
        """
        return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}

    @app.get("/ready")
    async def readiness() -> JSONResponse:
        """Readiness probe - can the server handle requests?

        Checks:
        - BunkerWeb API connectivity
        - Search service availability (if remote mode)

        Returns:
            Readiness status with individual check results
        """
        checks: dict[str, bool] = {
            "bunkerweb_api": False,
            "search_service": False,
        }

        # Check BunkerWeb API
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(f"{settings.bunkerweb_base_url}/ping", timeout=5.0)
                checks["bunkerweb_api"] = response.status_code == 200
        except Exception:  # noqa: S110
            pass

        # Check search service
        if settings.search_mode == "remote":
            try:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(
                        f"{settings.search_api_url}/health", timeout=5.0
                    )
                    checks["search_service"] = response.status_code == 200
            except Exception:  # noqa: S110
                pass
        else:
            checks["search_service"] = True  # Local mode always ready

        all_ready = all(checks.values())
        status_code = 200 if all_ready else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if all_ready else "not_ready",
                "checks": checks,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    return app


app = create_app()
