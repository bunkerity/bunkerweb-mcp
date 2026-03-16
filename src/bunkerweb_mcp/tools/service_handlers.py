"""Service management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..cache import CACHE_TTL, get_cached, invalidate_cache
from ..config import get_settings
from ..schemas.services import ServiceCreateRequest, ServiceUpdateRequest

if TYPE_CHECKING:
    from .params import (
        BunkerWebClientProtocol,
        DeleteServiceParams,
        GetServiceParams,
        ListServicesParams,
        ServiceConvertParams,
        ServiceCreateParams,
        ServiceUpdateParams,
    )


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_list_services(
    client: BunkerWebClientProtocol, params: ListServicesParams
) -> dict[str, Any]:
    """List configured services.

    This tool retrieves all BunkerWeb services (virtual hosts/server blocks).
    Optionally includes draft services that haven't been published yet.
    Results are cached if caching is enabled.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - with_drafts: Include draft services (default: True)

    Returns:
        API response dict with:
            - data: List of service objects with server_name, variables, state
            - count: Total number of services

    Raises:
        ToolExecutionError: If API request fails

    Examples:
        >>> await handle_list_services(client, ListServicesParams(with_drafts=True))
        {"data": [{"server_name": "example.com", "is_draft": False}]}
    """
    settings = get_settings()
    if settings.cache_enabled:
        cache_key = f"list_services:{params.with_drafts}"

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.list_services(with_drafts=params.with_drafts)
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            cache_key, CACHE_TTL["list_services"], fetch_and_serialize
        )
    response = await client.list_services(with_drafts=params.with_drafts)
    return _serialize_response(response)


async def handle_get_service(
    client: BunkerWebClientProtocol, params: GetServiceParams
) -> dict[str, Any]:
    """Fetch configuration for a specific service.

    This tool retrieves detailed configuration for a single BunkerWeb service,
    including variables, security settings, and metadata.
    Results are cached if caching is enabled.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - service: Service identifier (server_name)
            - full: Include derived defaults (default: False)
            - methods: Include method metadata (default: True)
            - with_drafts: Search in draft services (default: True)

    Returns:
        API response dict with:
            - data: Service configuration object
            - variables: Key-value configuration pairs
            - metadata: Service metadata

    Raises:
        ToolExecutionError: If service not found or API request fails
        ToolValidationError: If service name is invalid

    Examples:
        >>> await handle_get_service(client, GetServiceParams(
        ...     service="example.com",
        ...     full=True
        ... ))
        {"data": {"server_name": "example.com", "variables": {...}}}
    """
    settings = get_settings()
    if settings.cache_enabled:
        cache_key = (
            f"get_service:{params.service}:{params.full}:{params.methods}:{params.with_drafts}"
        )

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.get_service(
                params.service,
                full=params.full,
                methods=params.methods,
                with_drafts=params.with_drafts,
            )
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            cache_key, CACHE_TTL["get_service"], fetch_and_serialize
        )
    response = await client.get_service(
        params.service,
        full=params.full,
        methods=params.methods,
        with_drafts=params.with_drafts,
    )
    return _serialize_response(response)


async def handle_create_service(
    client: BunkerWebClientProtocol, params: ServiceCreateParams
) -> dict[str, Any]:
    """Create a new service.

    This tool creates a new BunkerWeb service (virtual host).
    Services can be created in draft mode for testing before going live.
    Invalidates service cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Service creation parameters containing:
            - server_name: Primary server name (required)
            - is_draft: Create as draft (default: False)
            - variables: Service-specific configuration variables (optional)

    Returns:
        API response dict with:
            - data: Created service object
            - status: Creation status
            - message: Confirmation message

    Raises:
        ToolExecutionError: If service already exists or creation fails
        ToolValidationError: If server_name is invalid or variables malformed

    Examples:
        >>> await handle_create_service(client, ServiceCreateParams(
        ...     server_name="new.example.com",
        ...     is_draft=True,
        ...     variables={"USE_MODSECURITY": "yes"}
        ... ))
        {"data": {...}, "status": "created"}
    """
    payload = ServiceCreateRequest.model_validate(params.model_dump())
    response = await client.create_service(payload)
    # Invalidate service cache after mutation
    await invalidate_cache("services")
    return _serialize_response(response)


async def handle_update_service(
    client: BunkerWebClientProtocol, params: ServiceUpdateParams
) -> dict[str, Any]:
    """Update an existing service.

    This tool modifies configuration of an existing BunkerWeb service.
    Only provided fields will be updated. Variables are upserted (merged).
    Invalidates service cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Update parameters containing:
            - service: Existing service identifier (required)
            - server_name: Rename the service (optional)
            - is_draft: Toggle draft state (optional)
            - variables: Variables to upsert/merge (optional)

    Returns:
        API response dict with:
            - data: Updated service object
            - status: Update status
            - changed_fields: List of modified fields

    Raises:
        ToolExecutionError: If service not found or update fails
        ToolValidationError: If parameters are invalid

    Examples:
        >>> await handle_update_service(client, ServiceUpdateParams(
        ...     service="example.com",
        ...     variables={"USE_ANTIBOT": "javascript"}
        ... ))
        {"data": {...}, "status": "updated"}
    """
    payload = ServiceUpdateRequest.model_validate(
        params.model_dump(include={"server_name", "is_draft", "variables"}, exclude_none=True)
    )
    response = await client.update_service(params.service, payload)
    # Invalidate service cache after mutation
    await invalidate_cache("services")
    return _serialize_response(response)


async def handle_delete_service(
    client: BunkerWebClientProtocol, params: DeleteServiceParams
) -> dict[str, Any]:
    """Delete a service and its configuration.

    This tool removes a BunkerWeb service and all associated configuration
    snippets. This operation is permanent and cannot be undone.
    Invalidates service cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - service: Service identifier to delete

    Returns:
        API response dict with:
            - status: Deletion status
            - service: Deleted service identifier
            - message: Confirmation message

    Raises:
        ToolExecutionError: If service not found or deletion fails
        ToolValidationError: If service name is invalid

    Examples:
        >>> await handle_delete_service(client, DeleteServiceParams(
        ...     service="old.example.com"
        ... ))
        {"status": "deleted", "service": "old.example.com"}
    """
    response = await client.delete_service(params.service)
    # Invalidate service cache after mutation
    await invalidate_cache("services")
    return _serialize_response(response)


async def handle_convert_service(
    client: BunkerWebClientProtocol, params: ServiceConvertParams
) -> dict[str, Any]:
    """Convert a service between draft and online states.

    This tool toggles a service between draft (testing) and online (live)
    states. Converting to online publishes the service configuration.
    Invalidates service cache after mutation.

    Args:
        client: BunkerWeb API client instance
        params: Parameters containing:
            - service: Service identifier
            - convert_to: Target state ("online" or "draft")

    Returns:
        API response dict with:
            - status: Conversion status
            - service: Service identifier
            - new_state: Final state after conversion

    Raises:
        ToolExecutionError: If service not found or conversion fails
        ToolValidationError: If convert_to is not "online" or "draft"

    Examples:
        >>> await handle_convert_service(client, ServiceConvertParams(
        ...     service="test.example.com",
        ...     convert_to="online"
        ... ))
        {"status": "success", "new_state": "online"}
    """
    response = await client.convert_service(params.service, convert_to=params.convert_to)
    # Invalidate service cache after mutation
    await invalidate_cache("services")
    return _serialize_response(response)
