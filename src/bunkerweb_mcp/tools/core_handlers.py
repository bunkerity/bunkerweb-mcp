"""Core API handlers: ping_api, create_api_token."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .params import AuthParams, BunkerWebClientProtocol, EmptyParams


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_ping_api(client: BunkerWebClientProtocol, params: EmptyParams) -> dict[str, Any]:
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
        >>> await handle_ping_api(client, EmptyParams())
        {"status": "pong", "timestamp": "2024-01-15T10:30:00Z"}
    """
    response = await client.ping()
    return _serialize_response(response)


async def handle_create_api_token(
    client: BunkerWebClientProtocol, params: AuthParams
) -> dict[str, Any]:
    """Create a Biscuit API token through POST /auth.

    Sends the given username and password (or the client's own credentials when
    both are omitted) to BunkerWeb and returns the token. Other tools do not
    need it: the server authenticates every call itself. The token is a live
    credential; BunkerWeb ends its life after API_BISCUIT_TTL_SECONDS, and the
    response carries no expiry field. Needs an API user on BunkerWeb.

    Args:
        client: BunkerWeb API client instance
        params: Authentication parameters containing:
            - username: Optional username for Basic auth
            - password: Optional password for Basic auth
            - payload: Optional custom JSON payload for advanced auth

    Returns:
        API response dict with:
            - token: Biscuit token (masked when BUNKERWEB_REDACT_SECRETS=true)

    Raises:
        ToolExecutionError: If authentication fails or credentials are invalid
        ToolValidationError: If auth parameters are malformed

    Examples:
        >>> await handle_create_api_token(client, AuthParams(
        ...     username="admin",
        ...     password="secret"
        ... ))
        {"token": "biscuit_token_here"}
    """
    response = await client.authenticate(
        username=params.username,
        password=params.password,
        payload=params.payload,
    )
    return _serialize_response(response)
