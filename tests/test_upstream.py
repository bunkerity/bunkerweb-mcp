import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bunkerweb_mcp import upstream
from bunkerweb_mcp.config import get_settings
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.plugins import PluginsResponse
from bunkerweb_mcp.tools.params import PluginDeleteParams, PluginUploadParams
from bunkerweb_mcp.tools.plugin_handlers import handle_delete_plugin, handle_upload_plugins
from bunkerweb_mcp.upstream import (
    CatalogUnavailable,
    SettingInfo,
    UpstreamVersion,
    api_can_replace,
    get_setting_catalog,
    get_upstream_version,
    invalidate_setting_catalog,
    parse_version,
    rename_supported,
    reset_upstream_state,
)


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    reset_upstream_state()
    yield
    reset_upstream_state()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.6.17", UpstreamVersion(1, 6, 17)),
        ("1.6.15-rc1", UpstreamVersion(1, 6, 14)),
        ("1.7.0~alpha", UpstreamVersion(1, 6, 999)),
        ("dev", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_version(raw: str | None, expected: UpstreamVersion | None) -> None:
    assert parse_version(raw) == expected


@pytest.mark.parametrize(
    ("owner", "version", "allowed"),
    [
        ("api", None, True),
        ("default", None, True),
        ("ui", None, False),
        ("ui", UpstreamVersion(1, 6, 5), False),
        ("ui", UpstreamVersion(1, 6, 6), True),
        ("wizard", None, False),
        ("wizard", UpstreamVersion(1, 6, 13), False),
        ("wizard", UpstreamVersion(1, 6, 14), True),
        ("scheduler", UpstreamVersion(1, 6, 17), False),
        ("autoconf", UpstreamVersion(1, 6, 17), False),
        ("manual", UpstreamVersion(1, 6, 17), False),
        ("unknown", UpstreamVersion(1, 6, 17), False),
    ],
)
def test_api_can_replace(owner: str, version: UpstreamVersion | None, allowed: bool) -> None:
    assert api_can_replace(owner, version) is allowed


def test_rename_supported_cutoff() -> None:
    assert not rename_supported(None)
    assert not rename_supported(UpstreamVersion(1, 6, 14))
    assert rename_supported(UpstreamVersion(1, 6, 15))


@pytest.mark.asyncio
async def test_version_unknown_when_openapi_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(upstream.time, "monotonic", lambda: now)
    client = SimpleNamespace(
        base_url="http://one", get_openapi_version=AsyncMock(return_value=None)
    )
    assert await get_upstream_version(client) is None
    client.get_openapi_version.return_value = "1.6.17"
    now += 29
    assert await get_upstream_version(client) is None
    client.get_openapi_version.assert_awaited_once()
    now += 1
    assert await get_upstream_version(client) == UpstreamVersion(1, 6, 17)
    assert client.get_openapi_version.await_count == 2
    now += 599
    client.get_openapi_version.return_value = "1.6.14"
    assert await get_upstream_version(client) == UpstreamVersion(1, 6, 17)
    assert client.get_openapi_version.await_count == 2


@pytest.mark.asyncio
async def test_version_cache_per_base_url_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(upstream.time, "monotonic", lambda: now)
    first = SimpleNamespace(
        base_url="http://one", get_openapi_version=AsyncMock(return_value="1.6.17")
    )
    same = SimpleNamespace(
        base_url="http://one", get_openapi_version=AsyncMock(return_value="1.6.14")
    )
    other = SimpleNamespace(
        base_url="http://two", get_openapi_version=AsyncMock(return_value="1.6.14")
    )
    assert await get_upstream_version(first) == UpstreamVersion(1, 6, 17)
    assert await get_upstream_version(same) == UpstreamVersion(1, 6, 17)
    same.get_openapi_version.assert_not_awaited()
    assert await get_upstream_version(other) == UpstreamVersion(1, 6, 14)
    now += 600
    assert await get_upstream_version(same) == UpstreamVersion(1, 6, 14)


def catalog_client(base_url: str = "http://one") -> SimpleNamespace:
    return SimpleNamespace(
        base_url=base_url,
        list_plugins=AsyncMock(
            return_value=PluginsResponse(
                plugins=[
                    {"settings": {"USE_MODSECURITY": {"context": "multisite"}}},
                    {
                        "settings": {
                            "REVERSE_PROXY_HOST": {
                                "context": "multisite",
                                "multiple": "reverse-proxy",
                            }
                        }
                    },
                ]
            )
        ),
    )


@pytest.mark.asyncio
async def test_catalog_built_from_plugin_settings() -> None:
    client = catalog_client()
    assert await get_setting_catalog(client) == {
        "USE_MODSECURITY": SettingInfo(context="multisite", multiple=False),
        "REVERSE_PROXY_HOST": SettingInfo(context="multisite", multiple=True),
    }
    client.list_plugins.assert_awaited_once_with(plugin_type="all", with_data=False)


@pytest.mark.asyncio
async def test_catalog_unavailable_on_error() -> None:
    client = catalog_client()
    client.list_plugins.side_effect = RuntimeError("offline")
    with pytest.raises(CatalogUnavailable):
        await get_setting_catalog(client)


@pytest.mark.parametrize(
    "data",
    [
        None,
        [{}],
        [{"settings": []}],
        [{"settings": {"X": None}}],
        [{"settings": {"X": {}}}],
        [{"settings": {"X": {"context": 1}}}],
    ],
)
@pytest.mark.asyncio
async def test_catalog_unavailable_on_unexpected_shape(data: object) -> None:
    client = catalog_client()
    client.list_plugins.return_value = SimpleNamespace(data=data)
    with pytest.raises(CatalogUnavailable):
        await get_setting_catalog(client)


@pytest.mark.asyncio
async def test_catalog_refresh_refetches() -> None:
    client = catalog_client()
    await get_setting_catalog(client)
    await get_setting_catalog(client, refresh=True)
    assert client.list_plugins.await_count == 2


@pytest.mark.asyncio
async def test_catalog_cached_when_cache_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CACHE_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert not get_settings().cache_enabled
        client = catalog_client()
        await get_setting_catalog(client)
        await get_setting_catalog(client)
        client.list_plugins.assert_awaited_once()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_catalog_cache_per_base_url_expiry_and_invalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(upstream.time, "monotonic", lambda: now)
    first, same, other = catalog_client(), catalog_client(), catalog_client("http://two")
    await get_setting_catalog(first)
    await get_setting_catalog(same)
    same.list_plugins.assert_not_awaited()
    await get_setting_catalog(other)
    other.list_plugins.assert_awaited_once()
    now += 600
    await get_setting_catalog(same)
    same.list_plugins.assert_awaited_once()
    invalidate_setting_catalog()
    await get_setting_catalog(other)
    assert other.list_plugins.await_count == 2


@pytest.mark.parametrize("operation", ["upload", "delete"])
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.asyncio
async def test_plugin_upload_and_delete_invalidate_catalog(operation: str, fails: bool) -> None:
    client = catalog_client()
    await get_setting_catalog(client)
    mutation = AsyncMock(return_value=ApiResponse(status="success"))
    if fails:
        mutation.side_effect = RuntimeError("failed")
    client.upload_plugins = client.delete_plugin = mutation

    async def mutate() -> None:
        if operation == "upload":
            await handle_upload_plugins(
                client,
                PluginUploadParams(files=[{"filename": "plugin.zip", "content_base64": "eA=="}]),
            )
        else:
            await handle_delete_plugin(client, PluginDeleteParams(plugin_id="example"))

    if fails:
        with pytest.raises(RuntimeError, match="failed"):
            await mutate()
    else:
        await mutate()
    await get_setting_catalog(client)
    assert client.list_plugins.await_count == 2


@pytest.mark.asyncio
async def test_inflight_catalog_fetch_cannot_undo_plugin_invalidation() -> None:
    client = catalog_client()
    old_response = client.list_plugins.return_value
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch_plugins(**kwargs: object) -> PluginsResponse:
        if not started.is_set():
            started.set()
            await release.wait()
            return old_response
        return PluginsResponse(plugins=[])

    client.list_plugins.side_effect = fetch_plugins
    client.delete_plugin = AsyncMock(return_value=ApiResponse(status="success"))
    pending = asyncio.create_task(get_setting_catalog(client))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        await handle_delete_plugin(client, PluginDeleteParams(plugin_id="example"))
    finally:
        release.set()
        old_catalog = await pending

    assert "REVERSE_PROXY_HOST" in old_catalog
    assert await get_setting_catalog(client) == {}
    assert await get_setting_catalog(client) == {}
    assert client.list_plugins.await_count == 2
