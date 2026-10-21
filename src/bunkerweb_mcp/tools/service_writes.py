"""Validate service writes and report what the database actually stored."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..exceptions import BunkerWebError, ToolValidationError
from ..upstream import (
    CatalogUnavailable,
    SettingInfo,
    api_can_replace,
    get_setting_catalog,
    get_upstream_version,
    rename_supported,
)

if TYPE_CHECKING:
    from .params import BunkerWebClientProtocol, ServiceUpdateParams


@dataclass(frozen=True)
class Preflight:
    variables: dict[str, str]
    server_name: str | None
    is_draft: bool | None
    skipped: dict[str, str]


HINTS: dict[str, str] = {
    "owned:scheduler": "Set in the scheduler's environment (variables.env on Linux, environment: in Docker); change it there.",
    "owned:autoconf": "Set by autoconf labels or Kubernetes annotations; change it there.",
    "owned:ui": "Set in the web UI; edit it there.",
    "owned:wizard": "Set in the web UI; edit it there.",
    "owned:manual": "Managed outside the API.",
    "unknown": "Not a per-service setting on this BunkerWeb; check the exact uppercase name.",
    "prefixed": "Use the setting name without the service prefix.",
    "server_name_in_variables": "Use the server_name parameter to rename a service.",
    "rename_unsupported": "Renaming on this BunkerWeb version would lose the service's custom configs and cache; upgrade to 1.6.15 or later.",
    "not_matched": "Sent, but the database does not show the requested value.",
    "draft": "The service is a draft; it is not published until is_draft is false.",
    "read_failed": "The write was accepted but could not be read back; do not resend it.",
}


def _unavailable(what: str) -> ToolValidationError:
    return ToolValidationError(
        f"Validation unavailable: could not read {what} from BunkerWeb; nothing was sent."
    )


def _service_data(response: Any) -> dict[str, Any]:
    data = response.data
    if not isinstance(data, dict):
        raise ValueError("Expected service settings")
    for key, entry in data.items():
        if not isinstance(key, str) or not isinstance(_value(entry), (str, int, float, bool)):
            raise ValueError("Expected a setting name and value")
        if isinstance(entry, dict) and (
            ("method" in entry and not isinstance(entry["method"], str))
            or ("global" in entry and not isinstance(entry["global"], bool))
        ):
            raise ValueError("Expected setting ownership metadata")
    return data


def _per_service(key: str, catalog: dict[str, SettingInfo]) -> bool:
    setting = catalog.get(key)
    if setting is None:
        base, separator, suffix = key.rpartition("_")
        setting = catalog.get(base) if separator and suffix.isascii() and suffix.isdigit() else None
        if setting is None or not setting.multiple:
            return False
    return setting.context == "multisite"


async def preflight_update(
    client: BunkerWebClientProtocol, params: ServiceUpdateParams
) -> Preflight:
    """Read upstream facts and refuse or filter unsafe update fields before PATCH."""
    try:
        response = await client.read_global_config(full=True, methods=False)
        if not isinstance(response.data, dict) or not isinstance(
            response.data.get("MULTISITE"), str
        ):
            raise ValueError("Expected global settings")
        multisite = response.data["MULTISITE"]
    except Exception as exc:
        raise _unavailable("global settings") from exc
    try:
        service = _service_data(
            await client.get_service(params.service, full=True, methods=True, with_drafts=True)
        )
    except BunkerWebError as exc:
        if exc.status == 404:
            raise ToolValidationError(
                f"Service {params.service} not found; nothing was sent."
            ) from exc
        raise _unavailable("the service") from exc
    except Exception as exc:
        raise _unavailable("the service") from exc

    catalog: dict[str, SettingInfo] = {}
    if params.variables:
        try:
            catalog = await get_setting_catalog(client)
        except CatalogUnavailable as exc:
            raise _unavailable("the setting catalog") from exc
    version = await get_upstream_version(client)
    if multisite != "yes":
        raise ToolValidationError(
            "MULTISITE is not yes: per-service settings do not apply in single-site mode; nothing was sent."
        )

    variables: dict[str, str] = {}
    skipped: dict[str, str] = {}
    refreshed = False
    for key, requested in (params.variables or {}).items():
        if key == "SERVER_NAME":
            skipped[key] = "server_name_in_variables"
            continue
        if key.startswith(f"{params.service}_") or (
            params.server_name is not None and key.startswith(f"{params.server_name}_")
        ):
            skipped[key] = "prefixed"
            continue
        if not _per_service(key, catalog) and not refreshed:
            try:
                catalog = await get_setting_catalog(client, refresh=True)
            except CatalogUnavailable as exc:
                raise _unavailable("the setting catalog") from exc
            refreshed = True
        if not _per_service(key, catalog):
            skipped[key] = "unknown"
            continue
        entry = service.get(key)
        if (
            isinstance(entry, dict)
            and entry.get("global") is False
            and entry.get("method") != "default"
            and str(_value(entry)) != requested
            and not api_can_replace(entry.get("method", ""), version)
        ):
            skipped[key] = f"owned:{entry.get('method', '')}"
            continue
        variables[key] = requested

    server_name = params.server_name
    if server_name is not None and not rename_supported(version):
        skipped["server_name"] = "rename_unsupported"
        server_name = None
    if not variables and server_name is None and params.is_draft is None:
        raise ToolValidationError(
            "Nothing to send: " + ", ".join(f"{key} ({code})" for key, code in skipped.items())
        )
    return Preflight(variables, server_name, params.is_draft, skipped)


def _value(entry: Any) -> Any:
    value = entry["value"] if isinstance(entry, dict) else entry
    return "" if value is None else value


def _receipt(summary: str, db: str, issues: dict[str, str]) -> dict[str, Any]:
    receipt: dict[str, Any] = {"db": db}
    if issues:
        receipt["issues"] = issues
        codes = [code.removeprefix("skipped:") for code in issues.values()]
        hints = {code: HINTS[code] for code in codes if code in HINTS}
        if hints:
            receipt["hints"] = hints
    return {"summary": summary, "receipt": receipt}


async def build_receipt(
    client: BunkerWebClientProtocol, params: ServiceUpdateParams, sent: Preflight
) -> dict[str, Any]:
    """Compare only sent fields with an uncached read; never retry the write."""
    issues = {key: f"skipped:{code}" for key, code in sent.skipped.items()}
    target = sent.server_name if sent.server_name is not None else params.service
    try:
        service = _service_data(
            await client.get_service(target, full=True, methods=True, with_drafts=True)
        )
    except Exception:
        issues["verification"] = "read_failed"
        return _receipt("WRITE ACCEPTED. DB UNVERIFIED. LIVE UNVERIFIED.", "unverified", issues)

    version = await get_upstream_version(client)
    matched = int(sent.server_name is not None)
    sent_fields = dict(sent.variables)
    if sent.is_draft is not None:
        sent_fields["is_draft"] = "yes" if sent.is_draft else "no"
    for key, requested in sent_fields.items():
        stored_key = "IS_DRAFT" if key == "is_draft" else key
        entry = service.get(stored_key)
        if stored_key in service and str(_value(entry)) == requested:
            matched += 1
        elif isinstance(entry, dict) and not api_can_replace(entry.get("method", ""), version):
            issues[key] = f"owned:{entry.get('method', '')}"
        else:
            issues[key] = "not_matched"

    total = (
        len(params.variables or {})
        + int(params.server_name is not None)
        + int(params.is_draft is not None)
    )
    skipped = len(sent.skipped)
    verified = skipped == 0 and matched == total
    head = (
        f"DB VERIFIED ({matched}/{total} MATCH)."
        if verified
        else (
            f"DB PARTIAL ({matched}/{total} MATCH"
            + (f", {skipped} SKIPPED" if skipped else "")
            + ")."
        )
    )
    draft = _value(service.get("IS_DRAFT")) == "yes"
    if draft:
        issues["service"] = "draft"
    summary = head + (" DRAFT: NOT PUBLISHED." if draft else "") + " LIVE UNVERIFIED."
    return _receipt(summary, "verified" if verified else "partial", issues)
