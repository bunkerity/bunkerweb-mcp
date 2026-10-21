"""Preflight and database receipts for service updates."""

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, call, patch

import pytest

from bunkerweb_mcp.exceptions import BunkerWebError, ToolValidationError
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.plugins import PluginsResponse
from bunkerweb_mcp.schemas.services import ServiceResponse
from bunkerweb_mcp.tools.params import ServiceUpdateParams
from bunkerweb_mcp.tools.service_handlers import handle_update_service
from bunkerweb_mcp.tools.service_writes import Preflight, preflight_update
from bunkerweb_mcp.upstream import reset_upstream_state

pytestmark = pytest.mark.asyncio

SERVICE = "example.com"
VERIFIED = "DB VERIFIED (2/2 MATCH). LIVE UNVERIFIED."
PARTIAL = "DB PARTIAL (1/2 MATCH, 1 SKIPPED). LIVE UNVERIFIED."
CATALOG = {
    "USE_MODSECURITY": {"context": "multisite"},
    "LIMIT_REQ_RATE": {"context": "multisite"},
    "REVERSE_PROXY_HOST": {"context": "multisite", "multiple": ""},
    "MULTISITE": {"context": "global"},
}


@pytest.fixture(autouse=True)
def _reset_upstream() -> Iterator[None]:
    reset_upstream_state()
    yield
    reset_upstream_state()


def _row(value: str | None, method: str = "api", inherited: bool = False) -> dict[str, Any]:
    return {"value": value, "method": method, "global": inherited, "default": "", "template": None}


def _config(**entries: Any) -> dict[str, Any]:
    return {"SERVER_NAME": _row(SERVICE), "IS_DRAFT": _row("no", "default"), **entries}


def _client(
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    version: str | None = "1.6.17",
) -> Any:
    return SimpleNamespace(
        base_url="http://bw",
        read_global_config=AsyncMock(return_value=GlobalConfigResponse(data={"MULTISITE": "yes"})),
        get_service=AsyncMock(
            side_effect=[
                ServiceResponse(data=before if before is not None else _config()),
                ServiceResponse(
                    data=after
                    if after is not None
                    else _config(USE_MODSECURITY=_row("yes"), LIMIT_REQ_RATE=_row("10r/s"))
                ),
            ]
        ),
        list_plugins=AsyncMock(return_value=PluginsResponse(data=[{"settings": CATALOG}])),
        get_openapi_version=AsyncMock(return_value=version),
        update_service=AsyncMock(
            return_value=ServiceResponse(status="success", changed_plugins=[])
        ),
    )


async def _update(client: Any, **fields: Any) -> dict[str, Any]:
    result = await handle_update_service(client, ServiceUpdateParams(service=SERVICE, **fields))
    assert client.update_service.await_count == 1
    assert next(iter(result)) == "summary"
    assert result["status"] == "success"
    return result


async def _refused(client: Any, message: str, **fields: Any) -> None:
    with pytest.raises(ToolValidationError) as exc:
        await handle_update_service(client, ServiceUpdateParams(service=SERVICE, **fields))
    assert str(exc.value) == message
    assert client.update_service.await_count == 0


async def test_all_match_is_verified() -> None:
    client = _client()
    result = await _update(client, variables={"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "10r/s"})
    assert result["summary"] == VERIFIED
    assert result["receipt"] == {"db": "verified"}
    client.read_global_config.assert_awaited_once_with(full=True, methods=False)
    assert client.get_service.await_args_list == [
        call(SERVICE, full=True, methods=True, with_drafts=True),
        call(SERVICE, full=True, methods=True, with_drafts=True),
    ]


async def test_scheduler_owned_key_is_skipped_rest_sent() -> None:
    client = _client(before=_config(LIMIT_REQ_RATE=_row("1r/s", "scheduler")))
    result = await _update(client, variables={"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "10r/s"})
    assert client.update_service.await_args.args[1].variables == {"USE_MODSECURITY": "yes"}
    assert result["summary"] == PARTIAL
    assert result["receipt"]["issues"] == {"LIMIT_REQ_RATE": "skipped:owned:scheduler"}
    assert "owned:scheduler" in result["receipt"]["hints"]


@pytest.mark.parametrize(
    ("version", "skipped", "summary"),
    [("1.6.5", True, PARTIAL), ("1.6.6", False, VERIFIED), (None, True, PARTIAL)],
)
async def test_ui_owned_key_by_version(version: str | None, skipped: bool, summary: str) -> None:
    client = _client(before=_config(LIMIT_REQ_RATE=_row("1r/s", "ui")), version=version)
    result = await _update(client, variables={"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "10r/s"})
    assert ("LIMIT_REQ_RATE" not in client.update_service.await_args.args[1].variables) is skipped
    assert result["summary"] == summary


@pytest.mark.parametrize(
    ("version", "skipped", "summary"),
    [("1.6.13", True, PARTIAL), ("1.6.14", False, VERIFIED)],
)
async def test_wizard_owned_key_by_version(version: str, skipped: bool, summary: str) -> None:
    client = _client(before=_config(LIMIT_REQ_RATE=_row("1r/s", "wizard")), version=version)
    result = await _update(client, variables={"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "10r/s"})
    assert ("LIMIT_REQ_RATE" not in client.update_service.await_args.args[1].variables) is skipped
    assert result["summary"] == summary


async def test_unknown_and_lowercase_keys_skipped() -> None:
    client = _client()
    result = await _update(
        client,
        variables={"TYPO_SETTING": "yes", "use_modsecurity": "yes", "USE_MODSECURITY": "yes"},
    )
    assert result["summary"] == "DB PARTIAL (1/3 MATCH, 2 SKIPPED). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {
        "TYPO_SETTING": "skipped:unknown",
        "use_modsecurity": "skipped:unknown",
    }
    assert client.list_plugins.await_count == 2
    assert client.update_service.await_args.args[1].variables == {"USE_MODSECURITY": "yes"}


async def test_multiple_suffix_key_accepted() -> None:
    client = _client(after=_config(REVERSE_PROXY_HOST_1=_row("http://origin")))
    client.list_plugins.return_value = PluginsResponse(
        data=[
            {
                "settings": {
                    **CATALOG,
                    "REVERSE_PROXY_HOST": {"context": "multisite", "multiple": "yes"},
                }
            }
        ]
    )
    result = await _update(client, variables={"REVERSE_PROXY_HOST_1": "http://origin"})
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."
    assert client.update_service.await_args.args[1].variables == {
        "REVERSE_PROXY_HOST_1": "http://origin"
    }


async def test_prefixed_and_server_name_in_variables_skipped() -> None:
    client = _client()
    result = await _update(
        client,
        server_name="new.example.com",
        variables={
            "SERVER_NAME": SERVICE,
            f"{SERVICE}_USE_MODSECURITY": "yes",
            "new.example.com_USE_MODSECURITY": "yes",
            "USE_MODSECURITY": "yes",
        },
    )
    assert result["summary"] == "DB PARTIAL (2/5 MATCH, 3 SKIPPED). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {
        "SERVER_NAME": "skipped:server_name_in_variables",
        f"{SERVICE}_USE_MODSECURITY": "skipped:prefixed",
        "new.example.com_USE_MODSECURITY": "skipped:prefixed",
    }


async def test_skipped_key_equal_to_stored_is_not_verified() -> None:
    client = _client()
    result = await _update(client, variables={"SERVER_NAME": SERVICE, "USE_MODSECURITY": "yes"})
    assert result["summary"] == PARTIAL
    assert result["receipt"]["db"] == "partial"


@pytest.mark.parametrize("version", ["1.6.14"])
async def test_rename_below_1_6_15_skipped(version: str) -> None:
    client = _client(version=version)
    result = await _update(
        client, server_name="new.example.com", variables={"USE_MODSECURITY": "yes"}
    )
    assert result["summary"] == PARTIAL
    assert result["receipt"]["issues"] == {"server_name": "skipped:rename_unsupported"}
    assert client.update_service.await_args.args[1].server_name is None
    assert client.get_service.await_args.args == (SERVICE,)


async def test_rename_unknown_version_skipped() -> None:
    client = _client(version=None)
    result = await _update(
        client, server_name="new.example.com", variables={"USE_MODSECURITY": "yes"}
    )
    assert result["summary"] == PARTIAL
    assert result["receipt"]["issues"] == {"server_name": "skipped:rename_unsupported"}


async def test_rename_1_6_15_reads_new_name() -> None:
    client = _client(version="1.6.15")
    result = await _update(client, server_name="new.example.com")
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."
    assert client.update_service.await_args.args[0] == SERVICE
    client.get_service.assert_awaited_with(
        "new.example.com", full=True, methods=True, with_drafts=True
    )
    client.list_plugins.assert_not_awaited()


async def test_all_skipped_sends_nothing() -> None:
    client = _client()
    await _refused(
        client,
        "Nothing to send: SERVER_NAME (server_name_in_variables), TYPO (unknown)",
        variables={"SERVER_NAME": SERVICE, "TYPO": "x"},
    )


async def test_multisite_no_refuses() -> None:
    client = _client()
    client.read_global_config.return_value = GlobalConfigResponse(data={"MULTISITE": "no"})
    await _refused(
        client,
        "MULTISITE is not yes: per-service settings do not apply in single-site mode; nothing was sent.",
        is_draft=False,
    )


async def test_catalog_unavailable_refuses() -> None:
    client = _client()
    client.list_plugins.side_effect = BunkerWebError("catalog unavailable")
    await _refused(
        client,
        "Validation unavailable: could not read the setting catalog from BunkerWeb; nothing was sent.",
        variables={"USE_MODSECURITY": "yes"},
    )


async def test_global_read_failure_refuses() -> None:
    client = _client()
    client.read_global_config.side_effect = BunkerWebError("global unavailable")
    await _refused(
        client,
        "Validation unavailable: could not read global settings from BunkerWeb; nothing was sent.",
        is_draft=False,
    )


async def test_service_404_refuses() -> None:
    client = _client()
    client.get_service.side_effect = BunkerWebError("missing", status=404)
    await _refused(client, f"Service {SERVICE} not found; nothing was sent.", is_draft=False)


@pytest.mark.parametrize("response", [None, SimpleNamespace(data=[]), SimpleNamespace(data=None)])
@pytest.mark.parametrize("what", ["global settings", "the service"])
async def test_unexpected_read_shape_refuses(response: Any, what: str) -> None:
    client = _client()
    if what == "global settings":
        client.read_global_config.return_value = response
    else:
        client.get_service.side_effect = None
        client.get_service.return_value = response
    await _refused(
        client,
        f"Validation unavailable: could not read {what} from BunkerWeb; nothing was sent.",
        is_draft=False,
    )


async def test_service_read_failure_refuses() -> None:
    client = _client()
    client.get_service.side_effect = BunkerWebError("private upstream details", status=500)
    await _refused(
        client,
        "Validation unavailable: could not read the service from BunkerWeb; nothing was sent.",
        is_draft=False,
    )


@pytest.mark.parametrize(
    "entry", [None, _row("no", "default"), _row("no", "scheduler", True), _row("yes", "scheduler")]
)
async def test_default_and_equal_value_allowed(entry: dict[str, Any] | None) -> None:
    client = _client(before=_config(**({"USE_MODSECURITY": entry} if entry else {})))
    result = await _update(client, variables={"USE_MODSECURITY": "yes"})
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."
    assert client.update_service.await_args.args[1].variables == {"USE_MODSECURITY": "yes"}


async def test_draft_only_call() -> None:
    client = _client(after=_config(IS_DRAFT=_row("yes", "default")))
    result = await _update(client, is_draft=True)
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). DRAFT: NOT PUBLISHED. LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"service": "draft"}
    client.list_plugins.assert_not_awaited()


async def test_read_back_failure_is_write_accepted() -> None:
    client = _client()
    client.get_service.side_effect = [
        ServiceResponse(data=_config()),
        BunkerWebError("read failed"),
    ]
    result = await _update(client, variables={"SERVER_NAME": SERVICE, "USE_MODSECURITY": "yes"})
    assert result["summary"] == "WRITE ACCEPTED. DB UNVERIFIED. LIVE UNVERIFIED."
    assert result["receipt"]["db"] == "unverified"
    assert result["receipt"]["issues"] == {
        "SERVER_NAME": "skipped:server_name_in_variables",
        "verification": "read_failed",
    }
    assert "read_failed" in result["receipt"]["hints"]


@pytest.mark.parametrize(
    ("method", "code"), [("api", "not_matched"), ("scheduler", "owned:scheduler")]
)
async def test_older_api_silent_skip_is_partial(method: str, code: str) -> None:
    client = _client(after=_config(USE_MODSECURITY=_row("no", method)))
    result = await _update(client, variables={"USE_MODSECURITY": "yes"})
    assert result["summary"] == "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"USE_MODSECURITY": code}


@pytest.mark.parametrize(
    "entry",
    [
        {"value": "no"},
        {"value": "no", "global": False},
        {"value": "no", "global": False, "method": ""},
        _row("no", "default"),
        _row("no", "scheduler", True),
        {"value": "no", "method": "scheduler"},
    ],
)
async def test_readback_without_explicit_owner_is_not_matched(entry: dict[str, Any]) -> None:
    client = _client(after=_config(USE_MODSECURITY=entry))
    result = await _update(client, variables={"USE_MODSECURITY": "yes"})
    assert result["summary"] == "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"USE_MODSECURITY": "not_matched"}
    assert result["receipt"]["hints"] == {
        "not_matched": "Sent, but the database does not show the requested value."
    }


async def test_receipt_has_no_setting_values() -> None:
    client = _client(after=_config())
    result = await _update(client, variables={"USE_MODSECURITY": "private-requested-value"})
    assert result["summary"] == "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED."
    assert "private-requested-value" not in json.dumps([result["summary"], result["receipt"]])


async def test_preflight_interface_and_read_order() -> None:
    client = _client()
    parent = AsyncMock()
    for name in ("read_global_config", "get_service", "list_plugins", "get_openapi_version"):
        parent.attach_mock(getattr(client, name), name)
    sent = await preflight_update(
        client, ServiceUpdateParams(service=SERVICE, variables={"USE_MODSECURITY": "yes"})
    )
    assert sent == Preflight(
        variables={"USE_MODSECURITY": "yes"}, server_name=None, is_draft=None, skipped={}
    )
    assert [item[0] for item in parent.mock_calls] == [
        "read_global_config",
        "get_service",
        "list_plugins",
        "get_openapi_version",
    ]
    assert client.update_service.await_count == 0


async def test_cache_invalidated_before_readback() -> None:
    client = _client()
    with patch(
        "bunkerweb_mcp.tools.service_handlers.invalidate_cache", new_callable=AsyncMock
    ) as invalidate:

        async def read_service(*args: Any, **kwargs: Any) -> ServiceResponse:
            if client.update_service.await_count:
                invalidate.assert_awaited_once_with("services")
            return ServiceResponse(data=_config())

        client.get_service.side_effect = read_service
        result = await _update(client, is_draft=False)
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."


async def test_catalog_refresh_can_recognize_setting() -> None:
    client = _client()
    client.list_plugins.side_effect = [
        PluginsResponse(data=[{"settings": {}}]),
        PluginsResponse(data=[{"settings": CATALOG}]),
    ]
    result = await _update(client, variables={"USE_MODSECURITY": "yes"})
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."
    assert client.list_plugins.await_count == 2


@pytest.mark.parametrize("key", ["MULTISITE", "USE_MODSECURITY_1", "REVERSE_PROXY_HOST_bad"])
async def test_global_and_invalid_multiple_settings_are_unknown(key: str) -> None:
    client = _client()
    result = await _update(client, is_draft=False, variables={key: "yes"})
    assert result["summary"] == PARTIAL
    assert result["receipt"]["issues"] == {key: "skipped:unknown"}
    assert client.list_plugins.await_count == 2
    assert client.update_service.await_args.args[1].variables is None


async def test_catalog_refresh_failure_refuses() -> None:
    client = _client()
    client.list_plugins.side_effect = [PluginsResponse(data=[]), BunkerWebError("refresh failed")]
    await _refused(
        client,
        "Validation unavailable: could not read the setting catalog from BunkerWeb; nothing was sent.",
        variables={"UNKNOWN_SETTING": "yes"},
    )


@pytest.mark.parametrize("data", [None, [], {"USE_MODSECURITY": {}}])
async def test_malformed_readback_is_unverified(data: Any) -> None:
    client = _client()
    client.get_service.side_effect = [ServiceResponse(data=_config()), SimpleNamespace(data=data)]
    result = await _update(client, variables={"USE_MODSECURITY": "yes"})
    assert result["summary"] == "WRITE ACCEPTED. DB UNVERIFIED. LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"verification": "read_failed"}


async def test_scalar_readback_value_matches() -> None:
    client = _client(after=_config(LIMIT_REQ_RATE=123))
    result = await _update(client, variables={"LIMIT_REQ_RATE": "123"})
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."


async def test_draft_mismatch_is_partial() -> None:
    client = _client()
    result = await _update(client, is_draft=True)
    assert result["summary"] == "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"is_draft": "not_matched"}


async def test_patch_failure_does_not_read_back() -> None:
    client = _client()
    client.update_service.side_effect = BunkerWebError("write failed", status=500)
    with pytest.raises(BunkerWebError, match="write failed"):
        await handle_update_service(client, ServiceUpdateParams(service=SERVICE, is_draft=False))
    assert client.update_service.await_count == 1
    assert client.get_service.await_count == 1


@pytest.mark.parametrize(
    "entry",
    [
        {"value": "no", "method": [], "global": False},
        {"value": "no", "method": "scheduler", "global": "false"},
        {"value": [], "method": "api", "global": False},
    ],
)
async def test_malformed_setting_metadata_refuses(entry: dict[str, Any]) -> None:
    client = _client(before=_config(USE_MODSECURITY=entry))
    await _refused(
        client,
        "Validation unavailable: could not read the service from BunkerWeb; nothing was sent.",
        variables={"USE_MODSECURITY": "yes"},
    )


@pytest.mark.parametrize("entry", [_row(None), None])
async def test_unrelated_null_setting_does_not_block_update(entry: Any) -> None:
    config = _config(UNRELATED_SETTING=entry, LIMIT_REQ_RATE=_row("1r/s", "scheduler"))
    client = _client(before=config, after={**config, "USE_MODSECURITY": _row("yes")})
    result = await _update(client, variables={"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "10r/s"})
    assert result["summary"] == PARTIAL
    assert result["receipt"]["issues"] == {"LIMIT_REQ_RATE": "skipped:owned:scheduler"}
    assert client.update_service.await_args.args[1].variables == {"USE_MODSECURITY": "yes"}


@pytest.mark.parametrize("entry", [_row(None), None])
@pytest.mark.parametrize(
    ("requested", "summary", "receipt"),
    [
        ("", "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED.", {"db": "verified"}),
        (
            "yes",
            "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED.",
            {
                "db": "partial",
                "issues": {"USE_MODSECURITY": "not_matched"},
                "hints": {
                    "not_matched": "Sent, but the database does not show the requested value."
                },
            },
        ),
    ],
)
async def test_null_readback_matches_only_empty_value(
    entry: Any, requested: str, summary: str, receipt: dict[str, Any]
) -> None:
    client = _client(after=_config(USE_MODSECURITY=entry))
    result = await _update(client, variables={"USE_MODSECURITY": requested})
    assert result["summary"] == summary
    assert result["receipt"] == receipt


async def test_owned_null_setting_equal_to_empty_value_is_allowed() -> None:
    config = _config(USE_MODSECURITY=_row(None, "scheduler"))
    client = _client(before=config, after=config)
    result = await _update(client, variables={"USE_MODSECURITY": ""})
    assert result["summary"] == "DB VERIFIED (1/1 MATCH). LIVE UNVERIFIED."
    assert result["receipt"] == {"db": "verified"}
    assert client.update_service.await_args.args[1].variables == {"USE_MODSECURITY": ""}


async def test_missing_readback_key_does_not_match_empty_value() -> None:
    client = _client(after=_config())
    result = await _update(client, variables={"USE_MODSECURITY": ""})
    assert result["summary"] == "DB PARTIAL (0/1 MATCH). LIVE UNVERIFIED."
    assert result["receipt"]["issues"] == {"USE_MODSECURITY": "not_matched"}
