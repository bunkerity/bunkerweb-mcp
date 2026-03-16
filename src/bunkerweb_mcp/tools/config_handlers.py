"""Configuration management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..cache import CACHE_TTL, get_cached, invalidate_cache
from ..config import get_settings
from ..schemas.configs import (
    ConfigCreateRequest,
    ConfigKey,
    ConfigsDeleteRequest,
    ConfigUpdateRequest,
)

if TYPE_CHECKING:
    from .params import (
        BunkerWebClientProtocol,
        ConfigCreateParams,
        ConfigKeyParams,
        ConfigListParams,
        ConfigsDeleteParams,
        ConfigUpdateParams,
        ConfigUploadParams,
        ConfigUploadUpdateParams,
        GlobalConfigReadParams,
        GlobalConfigUpdateParams,
    )


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


def _build_config_key(params: ConfigKeyParams) -> ConfigKey:
    """Build a ConfigKey from params."""
    return ConfigKey(service=params.service, type=params.type, name=params.name)


async def handle_read_global_config(
    client: BunkerWebClientProtocol, params: GlobalConfigReadParams
) -> dict[str, Any]:
    """Read the global configuration values."""
    settings = get_settings()
    if settings.cache_enabled:
        cache_key = f"global_config_read:{params.full}:{params.methods}"

        async def fetch_and_serialize() -> dict[str, Any]:
            response = await client.read_global_config(full=params.full, methods=params.methods)
            return _serialize_response(response)

        return await get_cached(  # type: ignore[no-any-return]
            cache_key, CACHE_TTL["global_config_read"], fetch_and_serialize
        )
    response = await client.read_global_config(full=params.full, methods=params.methods)
    return _serialize_response(response)


async def handle_update_global_config(
    client: BunkerWebClientProtocol, params: GlobalConfigUpdateParams
) -> dict[str, Any]:
    """Update global configuration values."""
    response = await client.update_global_config(params.config)
    await invalidate_cache("global_config")
    return _serialize_response(response)


async def handle_list_configs(
    client: BunkerWebClientProtocol, params: ConfigListParams
) -> dict[str, Any]:
    """List custom configuration snippets."""
    response = await client.list_configs(
        service=params.service,
        config_type=params.type,
        with_drafts=params.with_drafts,
        with_data=params.with_data,
    )
    return _serialize_response(response)


async def handle_get_config(
    client: BunkerWebClientProtocol, params: ConfigKeyParams
) -> dict[str, Any]:
    """Fetch a specific configuration snippet."""
    key = _build_config_key(params)
    response = await client.get_config(key, with_data=True)
    return _serialize_response(response)


async def handle_create_config(
    client: BunkerWebClientProtocol, params: ConfigCreateParams
) -> dict[str, Any]:
    """Create a configuration snippet."""
    payload = ConfigCreateRequest.model_validate(params.model_dump())
    response = await client.create_config(payload)
    return _serialize_response(response)


async def handle_update_config(
    client: BunkerWebClientProtocol, params: ConfigUpdateParams
) -> dict[str, Any]:
    """Update or rename a configuration snippet."""
    key = _build_config_key(params)
    payload = ConfigUpdateRequest.model_validate(
        params.model_dump(
            include={"new_service", "new_type", "new_name", "data"}, exclude_none=True
        )
    )
    response = await client.update_config(key, payload)
    return _serialize_response(response)


async def handle_delete_config(
    client: BunkerWebClientProtocol, params: ConfigKeyParams
) -> dict[str, Any]:
    """Delete a specific configuration snippet."""
    key = _build_config_key(params)
    response = await client.delete_config(key)
    return _serialize_response(response)


async def handle_delete_configs_bulk(
    client: BunkerWebClientProtocol, params: ConfigsDeleteParams
) -> dict[str, Any]:
    """Delete multiple configuration snippets."""
    keys = [_build_config_key(item) for item in params.configs]
    request = ConfigsDeleteRequest(configs=keys)
    response = await client.delete_configs(request)
    return _serialize_response(response)


async def handle_upload_configs(
    client: BunkerWebClientProtocol, params: ConfigUploadParams
) -> dict[str, Any]:
    """Upload configuration snippets from file content."""
    files = [item.to_bytes() for item in params.files]
    response = await client.upload_configs(
        files=files,
        config_type=params.config_type,
        service=params.service,
    )
    return _serialize_response(response)


async def handle_update_config_upload(
    client: BunkerWebClientProtocol, params: ConfigUploadUpdateParams
) -> dict[str, Any]:
    """Update a configuration snippet using file upload."""
    key = _build_config_key(params)
    filename, content = params.file.to_bytes()
    response = await client.update_config_upload(
        key,
        file_name=filename,
        content=content,
        new_service=params.new_service,
        new_type=params.new_type,
        new_name=params.new_name,
    )
    return _serialize_response(response)
