"""Plugin management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from .params import (
        BunkerWebClientProtocol,
        PluginDeleteParams,
        PluginListParams,
        PluginUploadParams,
    )


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_list_plugins(
    client: BunkerWebClientProtocol, params: PluginListParams
) -> dict[str, Any]:
    """List installed plugins."""
    response = await client.list_plugins(plugin_type=params.type, with_data=params.with_data)
    return _serialize_response(response)


async def handle_upload_plugins(
    client: BunkerWebClientProtocol, params: PluginUploadParams
) -> dict[str, Any]:
    """Upload and install plugins from archives."""
    files = [item.to_bytes() for item in params.files]
    response = await client.upload_plugins(files=files, method=params.method)
    return _serialize_response(response)


async def handle_delete_plugin(
    client: BunkerWebClientProtocol, params: PluginDeleteParams
) -> dict[str, Any]:
    """Delete an installed plugin."""
    response = await client.delete_plugin(params.plugin_id)
    return _serialize_response(response)
