"""Read-only diagnostics for the connected BunkerWeb API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from ..upstream import parse_version

if TYPE_CHECKING:
    from .params import BunkerWebClientProtocol, DiagnoseParams


async def handle_diagnose(
    client: BunkerWebClientProtocol, params: DiagnoseParams
) -> dict[str, Any]:
    """Report independent upstream checks without returning setting values.

    Args:
        client: BunkerWeb API client instance.
        params: Optional service to inspect for draft state and ownership counts.

    Returns:
        A summary followed by diagnostics; failed reads never expose upstream errors.
    """
    host = urlsplit(client.base_url).netloc.rsplit("@", 1)[-1]
    reachable = False
    try:
        await client.ping()
        reachable = True
    except Exception:
        pass

    auth = False
    instances = None
    try:
        response = await client.list_instances()
        auth = True
        if not isinstance(response.data, list):
            raise ValueError("Expected an instance list")
        instances = {
            "total": len(response.data),
            "up": sum(instance.get("status") == "up" for instance in response.data),
        }
    except Exception:
        pass

    version = "unknown (strictest rules applied)"
    try:
        raw = await client.get_openapi_version()
        if raw is not None and parse_version(raw) is not None:
            version = raw
    except Exception:
        pass

    multisite = None
    try:
        config = await client.read_global_config(full=True, methods=False)
        if not isinstance(config.data, dict):
            raise ValueError("Expected global settings")
        value = config.data["MULTISITE"]
        if value in ("yes", "no"):
            multisite = value
    except Exception:
        pass

    service: dict[str, Any] | None = None
    if params.service is not None:
        service = {"exists": False, "draft": None, "owners": {}}
        try:
            settings = (
                await client.get_service(params.service, full=True, methods=True, with_drafts=True)
            ).data
            if not isinstance(settings, dict):
                raise ValueError("Expected service settings")
            owners: dict[str, int] = {}
            for entry in settings.values():
                if isinstance(entry, dict) and entry.get("global") is False:
                    method = entry.get("method")
                    if isinstance(method, str) and method != "default":
                        owners[method] = owners.get(method, 0) + 1
            draft = settings.get("IS_DRAFT", {}).get("value")
            service = {
                "exists": True,
                "draft": draft == "yes" if draft in ("yes", "no") else None,
                "owners": owners,
            }
        except Exception:
            pass

    parts = [
        f"API {'OK' if reachable else 'FAIL'}",
        f"AUTH {'OK' if auth else 'FAIL'}",
        f"MULTISITE={multisite if multisite is not None else '?'}",
        (
            f"{instances['total']} instances ({instances['up']} up)"
            if instances is not None
            else "instances FAIL"
        ),
    ]
    if service is not None:
        parts.append(f"SERVICE {'OK' if service['exists'] else 'FAIL'}")
    return {
        "summary": " · ".join(parts),
        "api": {"host": host, "reachable": reachable},
        "auth": auth,
        "version": version,
        "multisite": multisite,
        "instances": instances,
        "service": service,
        "live": "Live state cannot be checked on BunkerWeb 1.6.",
    }
