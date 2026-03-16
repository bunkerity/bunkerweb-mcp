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
        HostnameParams,
        InstanceCreateParams,
        InstancesDeleteParams,
        InstanceUpdateParams,
        ReloadParams,
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
    client: BunkerWebClientProtocol, params: EmptyParams
) -> dict[str, Any]:
    """Ping all registered instances.

    This tool sends ping requests to all registered BunkerWeb instances
    to verify their availability and network connectivity.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - results: Per-instance ping results with latency
            - summary: Aggregate statistics (reachable, unreachable counts)

    Raises:
        ToolExecutionError: If API request fails

    Examples:
        >>> await handle_ping_instances(client, EmptyParams())
        {"results": [...], "summary": {"reachable": 3, "unreachable": 0}}
    """
    response = await client.ping_instances()
    return _serialize_response(response)


async def handle_stop_instances(
    client: BunkerWebClientProtocol, params: EmptyParams
) -> dict[str, Any]:
    """Stop all registered instances.

    This tool sends stop commands to all registered BunkerWeb instances,
    gracefully shutting down nginx processes. Use with caution in production.

    Args:
        client: BunkerWeb API client instance
        params: Empty parameters (no input required)

    Returns:
        API response dict with:
            - stopped: List of successfully stopped instance hostnames
            - failed: List of instances that failed to stop
            - errors: Detailed error messages

    Raises:
        ToolExecutionError: If API request fails

    Examples:
        >>> await handle_stop_instances(client, EmptyParams())
        {"stopped": ["bw-1", "bw-2"], "failed": [], "errors": {}}
    """
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
            cache_key, CACHE_TTL["instance_get"], fetch_and_serialize
        )
    response = await client.get_instance(params.hostname)
    return _serialize_response(response)


async def handle_ping_instance(
    client: BunkerWebClientProtocol, params: SimpleHostnameParams
) -> dict[str, Any]:
    """Ping a specific instance.

    This tool sends a ping request to a single BunkerWeb instance
    to verify availability and measure network latency.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - hostname: Target instance hostname

    Returns:
        API response dict with:
            - status: Ping status ("success", "timeout", "unreachable")
            - latency_ms: Response latency in milliseconds
            - timestamp: Ping timestamp

    Raises:
        ToolExecutionError: If instance not found or network error
        ToolValidationError: If hostname is invalid

    Examples:
        >>> await handle_ping_instance(client, SimpleHostnameParams(hostname="bw-1"))
        {"status": "success", "latency_ms": 5, "timestamp": "..."}
    """
    response = await client.ping_instance(params.hostname)
    return _serialize_response(response)


async def handle_stop_instance(
    client: BunkerWebClientProtocol, params: SimpleHostnameParams
) -> dict[str, Any]:
    """Stop a specific instance.

    This tool sends a stop command to a single BunkerWeb instance,
    gracefully shutting down the nginx process.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - hostname: Target instance hostname to stop

    Returns:
        API response dict with:
            - status: Stop operation status
            - hostname: Stopped instance hostname
            - message: Confirmation or error message

    Raises:
        ToolExecutionError: If instance not found or stop fails
        ToolValidationError: If hostname is invalid

    Examples:
        >>> await handle_stop_instance(client, SimpleHostnameParams(hostname="bw-1"))
        {"status": "success", "hostname": "bw-1", "message": "Instance stopped"}
    """
    response = await client.stop_instance(params.hostname)
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


async def handle_delete_instance(
    client: BunkerWebClientProtocol, params: SimpleHostnameParams
) -> dict[str, Any]:
    """Delete a single instance.

    This tool unregisters a specific BunkerWeb instance by hostname.
    Instance should be stopped before deletion.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - hostname: Instance hostname to delete

    Returns:
        API response dict with:
            - status: Deletion status
            - hostname: Deleted instance hostname
            - message: Confirmation message

    Raises:
        ToolExecutionError: If instance not found or deletion fails
        ToolValidationError: If hostname is invalid

    Examples:
        >>> await handle_delete_instance(client, SimpleHostnameParams(hostname="bw-1"))
        {"status": "deleted", "hostname": "bw-1", "message": "Instance removed"}
    """
    response = await client.delete_instance(params.hostname)
    return _serialize_response(response)


async def handle_reload_instances(
    client: BunkerWebClientProtocol, params: ReloadParams
) -> dict[str, Any]:
    """Trigger configuration reload across all instances.

    This tool reloads BunkerWeb configuration on all registered instances.
    Use test=True to validate configuration syntax before applying changes.

    Args:
        client: BunkerWeb API client instance
        params: Reload parameters containing:
            - test: Run in validation-only mode (default: True)

    Returns:
        API response dict with:
            - status: Reload status ("success", "failed", "validation_error")
            - results: Per-instance reload results
            - errors: Configuration or reload errors

    Raises:
        ToolExecutionError: If reload fails or syntax errors detected
        ToolValidationError: If parameters are invalid

    Examples:
        >>> await handle_reload_instances(client, ReloadParams(test=True))
        {"status": "success", "results": [...], "errors": {}}
    """
    response = await client.reload_instances(test=params.test)
    return _serialize_response(response)


async def handle_reload_instance(
    client: BunkerWebClientProtocol, params: HostnameParams
) -> dict[str, Any]:
    """Trigger configuration reload on a single instance.

    This tool reloads BunkerWeb configuration on a specific instance.
    Use test=True to validate syntax before applying changes.

    Args:
        client: BunkerWeb API client instance
        params: Reload parameters containing:
            - hostname: Target instance hostname
            - test: Run in validation-only mode (default: True)

    Returns:
        API response dict with:
            - status: Reload status
            - hostname: Target instance
            - output: nginx reload output
            - errors: Syntax or reload errors

    Raises:
        ToolExecutionError: If instance not found or reload fails
        ToolValidationError: If parameters are invalid

    Examples:
        >>> await handle_reload_instance(client, HostnameParams(
        ...     hostname="bw-1",
        ...     test=False
        ... ))
        {"status": "success", "hostname": "bw-1", "output": "..."}
    """
    response = await client.reload_instance(hostname=params.hostname, test=params.test)
    return _serialize_response(response)
