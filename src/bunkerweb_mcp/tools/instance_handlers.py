"""Instance management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..cache import CACHE_TTL, get_cached
from ..config import get_settings
from ..schemas.instances import (
    InstanceCreateRequest,
    InstancesDeleteRequest,
    InstanceUpdateRequest,
)

if TYPE_CHECKING:
    from .params import (
        BunkerWebClientProtocol,
        EmptyParams,
        InstanceCreateParams,
        InstancesDeleteParams,
        InstanceTargetParams,
        InstanceUpdateParams,
        OptionalHostnameParams,
        ReloadInstancesParams,
        SimpleHostnameParams,
    )


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_list_instances(
    client: BunkerWebClientProtocol, params: EmptyParams
) -> dict[str, Any]:
    """List registered BunkerWeb instances.

    This tool retrieves all BunkerWeb instances currently registered with
    the scheduler/controller. Results are cached if caching is enabled.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - data: List of instance objects with hostname, status, metadata
            - count: Total number of instances

    Raises:
        ToolExecutionError: If API request fails

    Examples:
        >>> await handle_list_instances(client, EmptyParams())
        {"data": [{"hostname": "bw-1", "status": "active"}], "count": 1}
    """
    settings = get_settings()
    if settings.cache_enabled:

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.list_instances()
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            "list_instances", CACHE_TTL["list_instances"], fetch_and_serialize
        )
    response = await client.list_instances()
    return _serialize_response(response)


async def handle_ping_instances(
    client: BunkerWebClientProtocol, params: OptionalHostnameParams
) -> dict[str, Any]:
    """Ping one instance, or every registered instance when no hostname is given.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - hostname: Optional instance hostname; omit to ping all instances

    Returns:
        API response dict with the live ping result of the targeted instances.

    Raises:
        ToolExecutionError: If the instance is not found or the API request fails

    Examples:
        >>> await handle_ping_instances(client, OptionalHostnameParams(hostname="bw-1"))
        {"status": "success", ...}
    """
    if params.hostname is not None:
        response = await client.ping_instance(params.hostname)
    else:
        response = await client.ping_instances()
    return _serialize_response(response)


async def handle_stop_instances(
    client: BunkerWebClientProtocol, params: InstanceTargetParams
) -> dict[str, Any]:
    """Stop one instance, or every registered instance with all=true.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing exactly one of:
            - hostname: Target instance hostname
            - all: True to stop every registered instance

    Returns:
        API response dict with the stop result of the targeted instances.

    Raises:
        ToolExecutionError: If the instance is not found or the stop fails
        ToolValidationError: If neither or both of hostname and all are given

    Examples:
        >>> await handle_stop_instances(client, InstanceTargetParams(hostname="bw-1"))
        {"status": "success", ...}
    """
    if params.hostname is not None:
        response = await client.stop_instance(params.hostname)
    else:
        response = await client.stop_instances()
    return _serialize_response(response)


async def handle_get_instance(
    client: BunkerWebClientProtocol, params: SimpleHostnameParams
) -> dict[str, Any]:
    """Fetch details for a specific instance.

    This tool retrieves comprehensive configuration and status information
    for a single BunkerWeb instance by hostname. Results are cached.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - hostname: Target instance hostname

    Returns:
        API response dict with:
            - data: Instance object with full configuration
            - hostname: Instance hostname
            - status: Current status
            - metadata: Additional instance metadata

    Raises:
        ToolExecutionError: If instance not found or API request fails
        ToolValidationError: If hostname is invalid

    Examples:
        >>> await handle_get_instance(client, SimpleHostnameParams(hostname="bw-1"))
        {"data": {"hostname": "bw-1", "status": "active", ...}}
    """
    settings = get_settings()
    if settings.cache_enabled:
        cache_key = f"instance_get:{params.hostname}"

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.get_instance(params.hostname)
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            cache_key, CACHE_TTL["get_instance"], fetch_and_serialize
        )
    response = await client.get_instance(params.hostname)
    return _serialize_response(response)


async def handle_create_instance(
    client: BunkerWebClientProtocol, params: InstanceCreateParams
) -> dict[str, Any]:
    """Create a new instance.

    This tool registers a new BunkerWeb instance with the scheduler/controller.
    The instance must be running and reachable before registration.

    Args:
        client: BunkerWeb API client instance
        params: Instance creation parameters containing:
            - hostname: Unique instance hostname (required)
            - name: Friendly display name (optional)
            - port: HTTP port (default: 8080)
            - listen_https: Enable HTTPS listener (optional)
            - https_port: HTTPS port (default: 8443)
            - server_name: Default server name (optional)
            - method: Registration method (optional)

    Returns:
        API response dict with:
            - data: Created instance object
            - status: Creation status
            - message: Confirmation message

    Raises:
        ToolExecutionError: If instance already exists or creation fails
        ToolValidationError: If required parameters are missing or invalid

    Examples:
        >>> await handle_create_instance(client, InstanceCreateParams(
        ...     hostname="bw-new",
        ...     port=8080,
        ...     listen_https=True
        ... ))
        {"data": {"hostname": "bw-new", ...}, "status": "created"}
    """
    payload = InstanceCreateRequest.model_validate(params.model_dump(exclude_none=True))
    response = await client.create_instance(payload)
    return _serialize_response(response)


async def handle_update_instance(
    client: BunkerWebClientProtocol, params: InstanceUpdateParams
) -> dict[str, Any]:
    """Update instance properties.

    This tool modifies configuration properties of an existing BunkerWeb
    instance. Only provided fields will be updated.

    Args:
        client: BunkerWeb API client instance
        params: Update parameters containing:
            - hostname: Target instance hostname (required)
            - name: New friendly name (optional)
            - port: New HTTP port (optional)
            - listen_https: Toggle HTTPS (optional)
            - https_port: New HTTPS port (optional)
            - server_name: New server name (optional)
            - method: Update method (optional)

    Returns:
        API response dict with:
            - data: Updated instance object
            - status: Update status
            - changed_fields: List of modified fields

    Raises:
        ToolExecutionError: If instance not found or update fails
        ToolValidationError: If parameters are invalid

    Examples:
        >>> await handle_update_instance(client, InstanceUpdateParams(
        ...     hostname="bw-1",
        ...     port=9090
        ... ))
        {"data": {...}, "status": "updated", "changed_fields": ["port"]}
    """
    payload = InstanceUpdateRequest.model_validate(
        params.model_dump(exclude={"hostname"}, exclude_none=True)
    )
    response = await client.update_instance(params.hostname, payload)
    return _serialize_response(response)


async def handle_delete_instances(
    client: BunkerWebClientProtocol, params: InstancesDeleteParams
) -> dict[str, Any]:
    """Delete multiple instances in a single call.

    This tool unregisters multiple BunkerWeb instances simultaneously.
    Instances must be stopped before deletion to prevent orphaned processes.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - instances: List of instance hostnames to delete

    Returns:
        API response dict with:
            - deleted: List of successfully deleted hostnames
            - failed: List of hostnames that failed to delete
            - errors: Per-hostname error messages

    Raises:
        ToolExecutionError: If API request fails
        ToolValidationError: If hostname list is empty or invalid

    Examples:
        >>> await handle_delete_instances(client, InstancesDeleteParams(
        ...     instances=["bw-1", "bw-2"]
        ... ))
        {"deleted": ["bw-1", "bw-2"], "failed": [], "errors": {}}
    """
    payload = InstancesDeleteRequest.model_validate(params.model_dump())
    response = await client.delete_instances(payload)
    return _serialize_response(response)


async def handle_reload_instances(
    client: BunkerWebClientProtocol, params: ReloadInstancesParams
) -> dict[str, Any]:
    """Reload configuration on one instance, or on every instance with all=true.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing exactly one of:
            - hostname: Target instance hostname
            - all: True to reload every registered instance
          and:
            - test: Test the configuration first (default: True); the reload still happens

    Returns:
        API response dict with the reload result of the targeted instances.

    Raises:
        ToolExecutionError: If the instance is not found or the reload fails
        ToolValidationError: If neither or both of hostname and all are given

    Examples:
        >>> await handle_reload_instances(client, ReloadInstancesParams(hostname="bw-1"))
        {"status": "success", ...}
    """
    if params.hostname is not None:
        response = await client.reload_instance(params.hostname, test=params.test)
    else:
        response = await client.reload_instances(test=params.test)
    return _serialize_response(response)
