"""Tests for the optional secret redaction policy."""

import base64
import copy
import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from asgi import WebSocketSession
from fastapi import FastAPI
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from bunkerweb_mcp.client import BunkerWebClient
from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.exceptions import BunkerWebError, ToolExecutionError, ToolValidationError
from bunkerweb_mcp.main import create_app
from bunkerweb_mcp.mcp_adapter import create_fastmcp_server
from bunkerweb_mcp.redaction import (
    DEFAULT_REDACT_PATTERN,
    REDACTED,
    RedactionPolicy,
    effective_cache_file_name,
    policy_from_settings,
)
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.core import AuthResponse
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.services import ServiceResponse
from bunkerweb_mcp.tools import Tools
from bunkerweb_mcp.tools.params import ConfigUploadParams

FAKE_SECRET = "fake-token-for-tests"

POLICY = RedactionPolicy()

# Every setting typed "password" in BunkerWeb 1.6 plugin.json files, plus the
# private key file settings, API_TOKEN and DATABASE_URI.
SENSITIVE_SETTINGS = [
    "ANTIBOT_IGNORE_HEADER_VALUE",
    "ANTIBOT_RECAPTCHA_SECRET",
    "ANTIBOT_RECAPTCHA_API_KEY",
    "ANTIBOT_HCAPTCHA_SECRET",
    "ANTIBOT_TURNSTILE_SECRET",
    "ANTIBOT_MCAPTCHA_SECRET",
    "ANTIBOT_CAPJS_SECRET",
    "AUTH_BASIC_PASSWORD",
    "BLACKLIST_HEADER_VALUE",
    "BLACKLIST_IGNORE_HEADER_VALUE",
    "COUNTRY_IGNORE_HEADER_VALUE",
    "CROWDSEC_API_KEY",
    "CROWDSEC_MANAGEMENT_PASSWORD",
    "DNSBL_IGNORE_HEADER_VALUE",
    "GREYLIST_HEADER_VALUE",
    "LETS_ENCRYPT_ZEROSSL_API_KEY",
    "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM",
    "PRO_LICENSE_KEY",
    "REDIS_PASSWORD",
    "REDIS_SENTINEL_PASSWORD",
    "ROBOTSTXT_DARKVISITORS_TOKEN",
    "SESSIONS_SECRET",
    "WHITELIST_HEADER_VALUE",
    "CUSTOM_SSL_KEY_DATA",
    "GRPC_SSL_KEY_DATA",
    "REVERSE_PROXY_SSL_KEY_DATA",
    "API_TOKEN",
    "DATABASE_URI",
    "DATABASE_URI_READONLY",
]

# Settings whose names look sensitive but whose values are not secrets.
NON_SENSITIVE_SETTINGS = [
    "LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64",
    "CORS_ALLOW_CREDENTIALS",
    "PROXY_CACHE_KEY",
    "CUSTOM_SSL_KEY",
    "ANTIBOT_RECAPTCHA_SITEKEY",
    "SERVER_NAME",
]


@pytest.fixture(autouse=True)
def _disable_response_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(CACHE_ENABLED=False)
    for module in ("service_handlers", "config_handlers"):
        monkeypatch.setattr(f"bunkerweb_mcp.tools.{module}.get_settings", lambda: settings)


def _setting(value: str, default: str = "") -> dict[str, Any]:
    return {"value": value, "global": False, "method": "ui", "default": default, "template": None}


def _tools(client: Any, policy: RedactionPolicy | None = POLICY) -> Tools:
    return Tools(client, redaction=policy)


async def _call(tools: Tools, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    handler = tools.get_tool(name)
    assert handler is not None
    return await handler(payload)


@pytest.mark.parametrize("key", SENSITIVE_SETTINGS)
def test_default_pattern_matches_sensitive_settings(key: str) -> None:
    assert POLICY.is_sensitive_key(key)


@pytest.mark.parametrize("key", NON_SENSITIVE_SETTINGS)
def test_default_pattern_ignores_non_sensitive_settings(key: str) -> None:
    assert not POLICY.is_sensitive_key(key)


def test_redact_flat_dict() -> None:
    data = {"REDIS_PASSWORD": FAKE_SECRET, "USE_REDIS": "yes"}

    assert POLICY.redact(data) == {"REDIS_PASSWORD": REDACTED, "USE_REDIS": "yes"}


def test_redact_methods_shape_keeps_metadata() -> None:
    data = {
        "AUTH_BASIC_PASSWORD": _setting(FAKE_SECRET, default="changeme"),
        "SESSIONS_SECRET": _setting(FAKE_SECRET),
        "SERVER_NAME": _setting("www.example.com"),
    }

    result = POLICY.redact(data)

    assert result["AUTH_BASIC_PASSWORD"] == {
        "value": REDACTED,
        "global": False,
        "method": "ui",
        "default": REDACTED,
        "template": None,
    }
    assert result["SESSIONS_SECRET"]["value"] == REDACTED
    assert result["SESSIONS_SECRET"]["default"] == ""
    assert result["SERVER_NAME"] == data["SERVER_NAME"]


def test_redact_suffixed_and_multisite_keys() -> None:
    data = {
        "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": FAKE_SECRET,
        "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM_1": FAKE_SECRET,
        "www.example.com_AUTH_BASIC_PASSWORD_2": FAKE_SECRET,
        "www.example.com_SERVER_NAME": "www.example.com",
    }

    result = POLICY.redact(data)

    assert result == {
        "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": REDACTED,
        "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM_1": REDACTED,
        "www.example.com_AUTH_BASIC_PASSWORD_2": REDACTED,
        "www.example.com_SERVER_NAME": "www.example.com",
    }


def test_redact_keeps_empty_values() -> None:
    data = {
        "REDIS_PASSWORD": "",
        "SESSIONS_SECRET": None,
        "API_TOKEN": [],
        "CROWDSEC_API_KEY": _setting(""),
    }

    assert POLICY.redact(data) == data


def test_redact_false_positive_is_left_visible() -> None:
    data = {"LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64": _setting("yes", default="yes")}

    assert POLICY.redact(data) == data


def test_redact_walks_lists_and_unknown_shapes_without_mutating() -> None:
    data = {
        "data": [
            {"REDIS_PASSWORD": FAKE_SECRET},
            {"API_TOKEN": {"nested": FAKE_SECRET, "list": [FAKE_SECRET, ""]}},
            {"DATABASE_URI": [FAKE_SECRET]},
        ],
        "status": "success",
    }
    original = copy.deepcopy(data)

    result = POLICY.redact(data)

    assert result == {
        "data": [
            {"REDIS_PASSWORD": REDACTED},
            {"API_TOKEN": {"nested": REDACTED, "list": [REDACTED, ""]}},
            {"DATABASE_URI": [REDACTED]},
        ],
        "status": "success",
    }
    assert data == original
    assert FAKE_SECRET not in json.dumps(result)


@pytest.mark.asyncio
async def test_disabled_redaction_returns_raw_output() -> None:
    payload = {"LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": _setting(FAKE_SECRET)}
    response = ServiceResponse(status="success", service="svc", data=payload)
    client = SimpleNamespace(get_service=AsyncMock(return_value=response))

    result = await _call(_tools(client, policy=None), "get_service", {"service": "svc"})

    assert result == response.model_dump(mode="json", exclude_none=True)
    assert result["data"]["LETS_ENCRYPT_DNS_CREDENTIAL_ITEM"]["value"] == FAKE_SECRET


@pytest.mark.asyncio
async def test_get_service_output_is_redacted() -> None:
    payload = {
        "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": _setting(FAKE_SECRET),
        "LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64": _setting("yes", default="yes"),
    }
    client = SimpleNamespace(
        get_service=AsyncMock(
            return_value=ServiceResponse(status="success", service="svc", data=payload)
        )
    )

    result = await _call(_tools(client), "get_service", {"service": "svc"})

    data = result["data"]
    assert data["LETS_ENCRYPT_DNS_CREDENTIAL_ITEM"]["value"] == REDACTED
    assert data["LETS_ENCRYPT_DNS_CREDENTIAL_ITEM"]["method"] == "ui"
    assert data["LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64"]["value"] == "yes"
    assert FAKE_SECRET not in json.dumps(result)


@pytest.mark.asyncio
async def test_update_service_with_sensitive_key_is_refused() -> None:
    client = SimpleNamespace(update_service=AsyncMock())

    with pytest.raises(ToolValidationError) as excinfo:
        await _call(
            _tools(client),
            "update_service",
            {"service": "svc", "variables": {"LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": FAKE_SECRET}},
        )

    message = str(excinfo.value)
    assert "BUNKERWEB_REDACT_SECRETS=true" in message
    assert "LETS_ENCRYPT_DNS_CREDENTIAL_ITEM" in message
    assert FAKE_SECRET not in message
    client.update_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_service_echoing_placeholder_is_refused() -> None:
    client = SimpleNamespace(update_service=AsyncMock())

    with pytest.raises(ToolValidationError, match=r"variables\.USE_ANTIBOT"):
        await _call(
            _tools(client),
            "update_service",
            {"service": "svc", "variables": {"USE_ANTIBOT": REDACTED}},
        )

    client.update_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_service_with_sensitive_key_is_refused() -> None:
    client = SimpleNamespace(create_service=AsyncMock())

    with pytest.raises(ToolValidationError, match="AUTH_BASIC_PASSWORD_1"):
        await _call(
            _tools(client),
            "create_service",
            {"server_name": "svc", "variables": {"AUTH_BASIC_PASSWORD_1": FAKE_SECRET}},
        )

    client.create_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_config_update_with_sensitive_key_is_refused() -> None:
    client = SimpleNamespace(update_global_config=AsyncMock())

    with pytest.raises(ToolValidationError, match="www.example.com_REDIS_PASSWORD"):
        await _call(
            _tools(client),
            "global_config_update",
            {"config": {"www.example.com_REDIS_PASSWORD": FAKE_SECRET, "USE_REDIS": "yes"}},
        )

    client.update_global_config.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "client_method"),
    [
        (
            "config_create",
            {"type": "http", "name": "snippet", "data": f"set $token {REDACTED};"},
            "create_config",
        ),
        (
            "config_update",
            {"type": "http", "name": "snippet", "data": f"set $token {REDACTED};"},
            "update_config",
        ),
        (
            "configs_upload",
            {
                "config_type": "http",
                "files": [
                    {
                        "filename": "a.conf",
                        "content_base64": base64.b64encode(
                            f"set $token {REDACTED};".encode()
                        ).decode(),
                    }
                ],
            },
            "upload_configs",
        ),
        (
            "config_upload_update",
            {
                "type": "http",
                "name": "snippet",
                "file": {
                    "filename": "a.conf",
                    "content_base64": base64.b64encode(REDACTED.encode()).decode(),
                },
            },
            "update_config_upload",
        ),
    ],
)
async def test_free_form_writes_with_placeholder_are_refused(
    tool: str, payload: dict[str, Any], client_method: str
) -> None:
    client_call = AsyncMock()
    client = SimpleNamespace(**{client_method: client_call})

    with pytest.raises(ToolValidationError, match=re.escape(REDACTED)):
        await _call(_tools(client), tool, payload)

    client_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_sensitive_write_is_forwarded() -> None:
    client = SimpleNamespace(
        update_service=AsyncMock(
            return_value=ServiceResponse(
                status="success",
                service="svc",
                data={"LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": FAKE_SECRET},
            )
        ),
        upload_configs=AsyncMock(return_value=ApiResponse(status="success")),
    )
    tools = _tools(client)

    result = await _call(
        tools,
        "update_service",
        {
            "service": "svc",
            "variables": {"LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64": "no", "USE_ANTIBOT": "no"},
        },
    )
    await _call(
        tools,
        "configs_upload",
        {
            "config_type": "http",
            "files": [{"filename": "a.conf", "content_base64": "Y29udGVudA=="}],
        },
    )

    payload = client.update_service.await_args_list[0].args[1]
    assert payload.variables == {
        "LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64": "no",
        "USE_ANTIBOT": "no",
    }
    assert result["data"]["LETS_ENCRYPT_DNS_CREDENTIAL_ITEM"] == REDACTED
    client.upload_configs.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin", "file_name"),
    [
        ("letsencrypt", "folder:/var/cache/bunkerweb/letsencrypt/etc.tgz"),
        ("LetsEncrypt", "credentials_0123456789ab.ini"),
        ("customcert", "cert.pem"),
        ("crowdsec", "crowdsec.conf"),
        ("misc", "default-server-cert.key"),
        ("reverseproxy", "client-key.pem"),
        ("bunkernet", "instance.id"),
    ],
)
async def test_cache_fetch_of_sensitive_files_is_refused(plugin: str, file_name: str) -> None:
    client = SimpleNamespace(fetch_cache_file=AsyncMock())

    with pytest.raises(ToolValidationError, match="private keys or credentials"):
        await _call(
            _tools(client),
            "cache_fetch_file",
            {"plugin": plugin, "job_name": "job", "file_name": file_name},
        )

    client.fetch_cache_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_fetch_of_other_files_is_forwarded() -> None:
    client = SimpleNamespace(
        fetch_cache_file=AsyncMock(return_value={"status": "success", "data": "1.2.3.4"})
    )

    result = await _call(
        _tools(client),
        "cache_fetch_file",
        {"plugin": "blacklist", "job_name": "blacklist-download", "file_name": "ip.list"},
    )

    assert result["data"] == "1.2.3.4"
    client.fetch_cache_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_list_masks_sensitive_entries() -> None:
    entries = [
        {"plugin": "letsencrypt", "file_name": "credentials_abc.ini", "data": FAKE_SECRET},
        {"plugin": "misc", "file_name": "default-server-cert.key", "data": FAKE_SECRET},
        {"plugin": "letsencrypt", "file_name": "empty.ini", "data": ""},
        {"plugin": "blacklist", "file_name": "ip.list", "data": "1.2.3.4"},
    ]
    client = SimpleNamespace(
        list_cache=AsyncMock(return_value=ApiResponse(status="success", data=entries))
    )

    result = await _call(_tools(client), "cache_list", {"with_data": True})

    assert [entry["data"] for entry in result["data"]] == [REDACTED, REDACTED, "", "1.2.3.4"]
    assert result["data"][0]["file_name"] == "credentials_abc.ini"


@pytest.mark.asyncio
async def test_cache_list_masks_nested_sensitive_entries() -> None:
    entries = [
        {
            "plugin_id": "letsencrypt",
            "file_name": "credentials_abc.ini",
            "data": FAKE_SECRET,
            "extra": [{"plugin_id": "customcert", "file_name": "a.key", "data": FAKE_SECRET}],
        }
    ]
    client = SimpleNamespace(
        list_cache=AsyncMock(return_value=ApiResponse(status="success", data=entries))
    )

    result = await _call(_tools(client), "cache_list", {"with_data": True})

    assert result["data"] == [
        {
            "plugin_id": "letsencrypt",
            "file_name": "credentials_abc.ini",
            "data": REDACTED,
            "extra": [{"plugin_id": "customcert", "file_name": "a.key", "data": REDACTED}],
        }
    ]


@pytest.mark.asyncio
async def test_authenticate_token_is_redacted() -> None:
    client = SimpleNamespace(
        authenticate=AsyncMock(return_value=AuthResponse(status="success", token=FAKE_SECRET))
    )

    result = await _call(_tools(client), "authenticate", {"username": "admin"})

    assert result == {"status": "success", "token": REDACTED}


@pytest.mark.asyncio
async def test_global_config_resource_is_redacted() -> None:
    client = SimpleNamespace(
        read_global_config=AsyncMock(
            return_value=GlobalConfigResponse(
                status="success",
                data={"REDIS_PASSWORD": FAKE_SECRET, "USE_REDIS": "yes"},
            )
        )
    )
    server = create_fastmcp_server(Settings(SEARCH_MODE="disabled"), _tools(client))

    contents = list(await server.read_resource("config://global"))  # type: ignore[arg-type]

    data = json.loads(contents[0].content)
    assert data["data"] == {"REDIS_PASSWORD": REDACTED, "USE_REDIS": "yes"}
    client.read_global_config.assert_awaited_once_with(full=True, methods=False)


@pytest.mark.asyncio
async def test_mcp_tool_call_reports_refused_write() -> None:
    client = SimpleNamespace(update_global_config=AsyncMock())
    server = create_fastmcp_server(Settings(SEARCH_MODE="disabled"), _tools(client))

    with pytest.raises(ToolError, match="SESSIONS_SECRET") as excinfo:
        await server.call_tool("global_config_update", {"config": {"SESSIONS_SECRET": FAKE_SECRET}})

    assert FAKE_SECRET not in str(excinfo.value)
    client.update_global_config.assert_not_awaited()


def test_malformed_base64_upload_is_left_to_the_handler() -> None:
    params = ConfigUploadParams.model_validate(
        {"config_type": "http", "files": [{"filename": "a.conf", "content_base64": "abcde"}]}
    )

    assert POLICY.find_sensitive_write("configs_upload", params) == []


def test_policy_from_settings_disabled_by_default() -> None:
    assert policy_from_settings(Settings()) is None


def test_policy_from_settings_uses_default_pattern() -> None:
    policy = policy_from_settings(Settings(BUNKERWEB_REDACT_SECRETS=True))

    assert policy is not None
    assert policy.pattern.pattern == DEFAULT_REDACT_PATTERN


def test_policy_from_settings_uses_custom_pattern() -> None:
    policy = policy_from_settings(
        Settings(BUNKERWEB_REDACT_SECRETS=True, BUNKERWEB_REDACT_PATTERN="MY_PLUGIN_KEY")
    )

    assert policy is not None
    assert policy.is_sensitive_key("www.example.com_MY_PLUGIN_KEY_1")
    assert not policy.is_sensitive_key("REDIS_PASSWORD")


def test_empty_redact_pattern_falls_back_to_default() -> None:
    assert Settings(BUNKERWEB_REDACT_PATTERN="").redact_pattern is None


def test_invalid_redact_pattern_fails_settings_validation() -> None:
    with pytest.raises(ValidationError, match="BUNKERWEB_REDACT_PATTERN"):
        Settings(BUNKERWEB_REDACT_PATTERN="(unclosed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin", "job_name", "file_name"),
    [
        ("bunkernet", "job", "%69nstance.id"),
        ("misc/../letsencrypt", "job", "credentials.ini"),
        ("misc", "x/../../letsencrypt/job", "credentials.ini"),
        ("misc", "job", "x/../../../letsencrypt/job/credentials.ini"),
        ("other", "job", "client%2ekey"),
        ("misc", "job", "folder:instance.id"),
        ("misc", "job", "folder:certs_client.key"),
    ],
)
async def test_cache_alias_inputs_never_reach_upstream(
    plugin: str, job_name: str, file_name: str
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "success", "data": FAKE_SECRET})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as async_client:
        client = BunkerWebClient(
            Settings.model_validate({"BUNKERWEB_BASE_URL": "http://testserver"}),
            client=async_client,
        )
        with pytest.raises(ToolValidationError):
            await _call(
                _tools(client),
                "cache_fetch_file",
                {"plugin": plugin, "job_name": job_name, "file_name": file_name},
            )
        await client.close()

    assert requests == []


def test_effective_cache_file_name() -> None:
    assert effective_cache_file_name("folder:instance.id") == "instance.id"
    assert effective_cache_file_name("folder:a_b_c.pem") == "a/b/c.pem"
    assert effective_cache_file_name("plain_name.txt") == "plain_name.txt"


UPSTREAM_SECRET = "review-synthetic-secret-17"

UpstreamHandler = Callable[[httpx.Request], httpx.Response]


def _error_body_response(error_body: str) -> UpstreamHandler:
    def handler(request: httpx.Request) -> httpx.Response:
        if error_body == "json":
            return httpx.Response(
                400, json={"status": "error", "message": f"REDIS_PASSWORD={UPSTREAM_SECRET}"}
            )
        return httpx.Response(400, text=f"REDIS_PASSWORD={UPSTREAM_SECRET}")

    return handler


def _upstream_settings(monkeypatch: pytest.MonkeyPatch, *, redact: bool = True) -> Settings:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        BUNKERWEB_REDACT_SECRETS=redact,
        BUNKERWEB_BASE_URL="http://upstream.invalid",
        SEARCH_MODE="disabled",
        CACHE_ENABLED=False,
        BUNKERWEB_MAX_RETRIES=1,
        MCP_ALLOWED_HOSTS="testserver",
    )
    monkeypatch.setattr("bunkerweb_mcp.main.get_settings", lambda: settings)
    for module in ("config_handlers", "service_handlers", "instance_handlers", "ban_handlers"):
        monkeypatch.setattr(f"bunkerweb_mcp.tools.{module}.get_settings", lambda: settings)
    return settings


@asynccontextmanager
async def _upstream_client(
    settings: Settings, handler: UpstreamHandler
) -> AsyncIterator[BunkerWebClient]:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://upstream.invalid"
    ) as upstream:
        yield BunkerWebClient(settings, client=upstream)


@asynccontextmanager
async def _running_app(
    monkeypatch: pytest.MonkeyPatch, handler: UpstreamHandler, *, redact: bool = True
) -> AsyncIterator[FastAPI]:
    settings = _upstream_settings(monkeypatch, redact=redact)
    async with _upstream_client(settings, handler) as client:
        monkeypatch.setattr("bunkerweb_mcp.main.BunkerWebClient", lambda settings: client)
        app = create_app()
        async with app.router.lifespan_context(app):
            yield app


async def _wire_text(app: FastAPI, path: str) -> str:
    """Return the raw reply of one global-config read over the given transport."""
    if path == "ws":
        async with WebSocketSession(app, "/ws") as ws:
            await ws.send_json({"id": 1, "tool": "global_config_read", "params": {}})
            return await ws.receive_text()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as http:
        if path == "rpc":
            response = await http.post(
                "/rpc", json={"id": 1, "tool": "global_config_read", "params": {}}
            )
            assert response.status_code == 502
            return response.text
        method, params = (
            ("tools/call", {"name": "global_config_read", "arguments": {}})
            if path == "mcp-tool"
            else ("resources/read", {"uri": "config://global"})
        )
        response = await http.post(
            "/mcp/",
            headers={"accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        assert response.status_code == 200
        return response.text


def _assert_nothing_logged(caplog: pytest.LogCaptureFixture) -> None:
    assert UPSTREAM_SECRET not in caplog.text
    for record in caplog.records:
        assert UPSTREAM_SECRET not in record.getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["rpc", "ws", "mcp-tool", "mcp-resource"])
@pytest.mark.parametrize("error_body", ["json", "text"])
async def test_upstream_error_body_is_withheld(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, path: str, error_body: str
) -> None:
    caplog.set_level(logging.DEBUG)

    async with _running_app(monkeypatch, _error_body_response(error_body)) as app:
        wire = await _wire_text(app, path)

    assert "HTTP 400" in wire
    assert "details withheld" in wire
    assert UPSTREAM_SECRET not in wire
    _assert_nothing_logged(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [503, 599])
async def test_upstream_5xx_is_withheld(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, code: int
) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text=f"REDIS_PASSWORD={UPSTREAM_SECRET}")

    async with _running_app(monkeypatch, handler) as app:
        wire = await _wire_text(app, "mcp-tool")

    assert f"HTTP {code}" in wire
    assert "details withheld" in wire
    assert UPSTREAM_SECRET not in wire
    _assert_nothing_logged(caplog)


@pytest.mark.asyncio
async def test_invalid_upstream_payload_is_generic(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    settings = _upstream_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 1234, "data": UPSTREAM_SECRET})

    async with _upstream_client(settings, handler) as client:
        server = create_fastmcp_server(settings, _tools(client))
        with pytest.raises(ToolError) as excinfo:
            await server.call_tool("global_config_read", {})

    assert str(excinfo.value).endswith("Unexpected tool execution error")
    assert UPSTREAM_SECRET not in str(excinfo.value)
    _assert_nothing_logged(caplog)


@pytest.mark.asyncio
async def test_local_error_message_passes_through(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = SimpleNamespace(
        ban=AsyncMock(side_effect=BunkerWebError("Ban payload must not be empty"))
    )

    with pytest.raises(ToolExecutionError, match="Ban payload must not be empty"):
        await _call(_tools(client), "ban_ip", {"bans": [{"ip": "192.0.2.1"}]})

    _assert_nothing_logged(caplog)


@pytest.mark.asyncio
async def test_errors_unchanged_when_redaction_off(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _running_app(monkeypatch, _error_body_response("json"), redact=False) as app:
        wire = await _wire_text(app, "rpc")

    assert f"REDIS_PASSWORD={UPSTREAM_SECRET}" in wire


@pytest.mark.asyncio
async def test_withheld_error_drops_cause(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = SimpleNamespace(
        read_global_config=AsyncMock(side_effect=RuntimeError(UPSTREAM_SECRET))
    )
    _, model, handler, _, _ = next(
        entry for entry in _tools(client).iter_registered() if entry[0] == "global_config_read"
    )

    with pytest.raises(ToolExecutionError) as excinfo:
        await handler(model.model_validate({}))

    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    assert UPSTREAM_SECRET not in str(excinfo.value)
    _assert_nothing_logged(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_nonstandard_upstream_status_keeps_the_status(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, redact: bool
) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(499, json={"status": "error", "message": f"token={UPSTREAM_SECRET}"})

    settings = _upstream_settings(monkeypatch, redact=redact)
    async with _upstream_client(settings, handler) as client:
        server = create_fastmcp_server(settings, _tools(client, policy_from_settings(settings)))
        with pytest.raises(ToolError) as excinfo:
            await server.call_tool("global_config_read", {})

    message = str(excinfo.value)
    if redact:
        assert "HTTP 499" in message
        assert "details withheld" in message
        assert UPSTREAM_SECRET not in message
        _assert_nothing_logged(caplog)
    else:
        assert f"token={UPSTREAM_SECRET}" in message
        assert "Unexpected tool execution error" not in message
