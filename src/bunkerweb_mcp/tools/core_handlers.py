"""Core API handlers: ping, health, authenticate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .params import AuthParams, BunkerWebClientProtocol, EmptyParams


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_ping(client: BunkerWebClientProtocol, params: EmptyParams) -> dict[str, Any]:
    """Check if the BunkerWeb API is reachable.

    This tool performs a lightweight connectivity check to verify that the
    BunkerWeb API endpoint is accessible and responding to requests.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - status: Connection status message
            - timestamp: Server timestamp (if available)

    Raises:
        ToolExecutionError: If network error occurs or API is unreachable

    Examples:
        >>> await handle_ping(client, EmptyParams())
        {"status": "pong", "timestamp": "2024-01-15T10:30:00Z"}
    """
    response = await client.ping()
    return _serialize_response(response)


async def handle_health(client: BunkerWebClientProtocol, params: EmptyParams) -> dict[str, Any]:
    """Retrieve the lightweight health probe from the API.

    This tool provides detailed health status information about the
    BunkerWeb API, including service availability and dependency checks.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - status: Overall health status ("healthy", "degraded", "unhealthy")
            - checks: Individual component health checks
            - uptime: Service uptime information

    Raises:
        ToolExecutionError: If API is unreachable or health check fails

    Examples:
        >>> await handle_health(client, EmptyParams())
        {"status": "healthy", "checks": {...}, "uptime": "72h"}
    """
    response = await client.health()
    return _serialize_response(response)


async def handle_authenticate(
    client: BunkerWebClientProtocol, params: AuthParams
) -> dict[str, Any]:
    """Authenticate against /auth to obtain a Biscuit token.

    This tool performs authentication with the BunkerWeb API using either
    HTTP Basic auth or custom payload authentication to obtain session tokens.

    Args:
        client: BunkerWeb API client instance
        params: Authentication parameters containing:
            - username: Optional username for Basic auth
            - password: Optional password for Basic auth
            - payload: Optional custom JSON payload for advanced auth

    Returns:
        API response dict with:
            - status: Authentication status
            - token: Biscuit token for subsequent API calls
            - expires_at: Token expiration timestamp

    Raises:
        ToolExecutionError: If authentication fails or credentials are invalid
        ToolValidationError: If auth parameters are malformed

    Examples:
        >>> await handle_authenticate(client, AuthParams(
        ...     username="admin",
        ...     password="secret"
        ... ))
        {"status": "success", "token": "biscuit_token_here"}
    """
    response = await client.authenticate(
        username=params.username,
        password=params.password,
        payload=params.payload,
    )
    return _serialize_response(response)
