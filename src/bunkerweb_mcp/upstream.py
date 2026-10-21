"""Cached upstream version and setting facts used to validate writes."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tools.params import BunkerWebClientProtocol


@dataclass(frozen=True, order=True)
class UpstreamVersion:
    major: int
    minor: int
    patch: int


@dataclass(frozen=True)
class SettingInfo:
    context: str
    multiple: bool


class CatalogUnavailable(Exception):  # noqa: N818 - public interface consumed by write handlers
    """The upstream setting catalog could not be read or validated."""


_TTL = 600
_versions: dict[str, tuple[float, UpstreamVersion | None]] = {}
_catalogs: dict[str, tuple[float, dict[str, SettingInfo]]] = {}
_catalog_generation = 0


def parse_version(raw: str | None) -> UpstreamVersion | None:
    if raw is None or (match := re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(.*)", raw)) is None:
        return None
    major, minor, patch = map(int, match.group(1, 2, 3))
    if match.group(4):
        if patch:
            patch -= 1
        else:
            minor -= 1
            patch = 999
    return UpstreamVersion(major, minor, patch)


async def get_upstream_version(client: BunkerWebClientProtocol) -> UpstreamVersion | None:
    cached = _versions.get(client.base_url)
    if cached is not None and time.monotonic() < cached[0]:
        return cached[1]
    try:
        version = parse_version(await client.get_openapi_version())
    except Exception:
        version = None
    _versions[client.base_url] = (time.monotonic() + _TTL, version)
    return version


def api_can_replace(owner: str, version: UpstreamVersion | None) -> bool:
    if owner in {"api", "default"}:
        return True
    if version is None:
        return False
    if owner == "ui":
        return version >= UpstreamVersion(1, 6, 6)
    if owner == "wizard":
        return version >= UpstreamVersion(1, 6, 14)
    return False


def rename_supported(version: UpstreamVersion | None) -> bool:
    return version is not None and version >= UpstreamVersion(1, 6, 15)


async def get_setting_catalog(
    client: BunkerWebClientProtocol, *, refresh: bool = False
) -> dict[str, SettingInfo]:
    cached = _catalogs.get(client.base_url)
    if not refresh and cached is not None and time.monotonic() < cached[0]:
        return cached[1]
    generation = _catalog_generation
    try:
        response = await client.list_plugins(plugin_type="all", with_data=False)
        if not isinstance(response.data, list):
            raise ValueError("Expected a plugin list")
        catalog: dict[str, SettingInfo] = {}
        for plugin in response.data:
            if not isinstance(plugin, dict) or not isinstance(plugin.get("settings"), dict):
                raise ValueError("Expected plugin settings")
            for setting_id, setting in plugin["settings"].items():
                if (
                    not isinstance(setting_id, str)
                    or not isinstance(setting, dict)
                    or not isinstance(setting.get("context"), str)
                ):
                    raise ValueError("Expected a setting ID and context")
                catalog[setting_id] = SettingInfo(
                    context=setting["context"], multiple=bool(setting.get("multiple"))
                )
    except Exception as exc:
        raise CatalogUnavailable("Upstream setting catalog is unavailable") from exc
    if generation == _catalog_generation:
        _catalogs[client.base_url] = (time.monotonic() + _TTL, catalog)
    return catalog


def invalidate_setting_catalog() -> None:
    global _catalog_generation
    _catalog_generation += 1
    _catalogs.clear()


def reset_upstream_state() -> None:
    """Clear both fact caches for test isolation."""
    _versions.clear()
    invalidate_setting_catalog()
