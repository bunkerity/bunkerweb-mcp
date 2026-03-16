"""Ban management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..cache import CACHE_TTL, get_cached, invalidate_cache
from ..config import get_settings

if TYPE_CHECKING:
    from .params import BanParams, BunkerWebClientProtocol, EmptyParams, UnbanParams


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_list_bans(client: BunkerWebClientProtocol, params: EmptyParams) -> dict[str, Any]:
    """List active bans across instances.

    This tool retrieves all currently active IP bans from BunkerWeb instances.
    Results include ban metadata like expiration, reason, and service scope.
    Results are cached if caching is enabled.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - data: List of ban objects with ip, exp, reason, service
            - count: Total number of active bans

    Raises:
        ToolExecutionError: If API request fails

    Examples:
        >>> await handle_list_bans(client, EmptyParams())
        {"data": [{"ip": "1.2.3.4", "exp": 3600, "reason": "brute force"}]}
    """
    settings = get_settings()
    if settings.cache_enabled:

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.list_bans()
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            "list_bans", CACHE_TTL["list_bans"], fetch_and_serialize
        )
    response = await client.list_bans()
    return _serialize_response(response)


async def handle_ban_ip(client: BunkerWebClientProtocol, params: BanParams) -> dict[str, Any]:
    """Ban one or multiple IP addresses.

    This tool adds IP addresses to the BunkerWeb ban list with configurable
    expiration times and reasons. Bans can be global or service-specific.
    Invalidates ban cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Ban configuration containing:
            - bans: List of ban requests, each with:
                - ip: IP address to ban (IPv4 or IPv6)
                - exp: Expiration in seconds (0 = permanent, default: 86400)
                - reason: Audit log reason (default: "api")
                - service: Optional service identifier (null = global)

    Returns:
        API response dict with:
            - status: Ban operation status
            - data: List of banned IPs with confirmation
            - errors: Any validation or execution errors

    Raises:
        ToolExecutionError: If API request fails or network error occurs
        ToolValidationError: If IP format is invalid or params malformed

    Examples:
        >>> await handle_ban_ip(client, BanParams(bans=[
        ...     {"ip": "1.2.3.4", "exp": 3600, "reason": "brute force"},
        ...     {"ip": "5.6.7.8", "exp": 0, "reason": "permanent ban"}
        ... ]))
        {"status": "success", "data": [...]}
    """
    response = await client.ban([item.to_model() for item in params.bans])
    # Invalidate bans cache after mutation
    await invalidate_cache("bans")
    result = _serialize_response(response)

    # Enrich error response with helpful message if API returned generic error
    if result.get("status") == "error" and not result.get("message"):
        result["message"] = (
            "The BunkerWeb API rejected the ban request. "
            "Common causes: IP already banned, invalid IP format, or instance configuration issues. "
            "Check the instance logs for detailed error information."
        )

    return result


async def handle_unban_ip(client: BunkerWebClientProtocol, params: UnbanParams) -> dict[str, Any]:
    """Remove one or multiple bans.

    This tool removes IP addresses from the BunkerWeb ban list.
    Bans can be removed globally or from specific services.
    Invalidates ban cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Unban configuration containing:
            - bans: List of unban requests, each with:
                - ip: IP address to unban
                - service: Optional service identifier (null = global)

    Returns:
        API response dict with:
            - status: Unban operation status
            - data: List of unbanned IPs with confirmation
            - errors: Any errors that occurred

    Raises:
        ToolExecutionError: If API request fails
        ToolValidationError: If IP format is invalid

    Examples:
        >>> await handle_unban_ip(client, UnbanParams(bans=[
        ...     {"ip": "1.2.3.4", "service": None}
        ... ]))
        {"status": "success", "data": [...]}
    """
    response = await client.unban([item.to_model() for item in params.bans])
    # Invalidate bans cache after mutation
    await invalidate_cache("bans")
    result = _serialize_response(response)

    # Enrich error response with helpful message if API returned generic error
    if result.get("status") == "error" and not result.get("message"):
        result["message"] = (
            "The BunkerWeb API rejected the unban request. "
            "Common causes: IP not currently banned, invalid IP format, or instance configuration issues. "
            "Check the instance logs for detailed error information."
        )

    return result
