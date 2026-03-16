import base64
from http import HTTPStatus
from ipaddress import IPv4Address
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from bunkerweb_mcp.client import BunkerWebClient
from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.exceptions import BunkerWebError
from bunkerweb_mcp.schemas.bans import BanRequestModel, BansResponse, UnbanRequestModel
from bunkerweb_mcp.schemas.cache import CacheFileKey, CacheFilesDeleteRequest, CacheResponse
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.configs import (
    ConfigCreateRequest,
    ConfigKey,
    ConfigResponse,
    ConfigsDeleteRequest,
    ConfigsResponse,
    ConfigUpdateRequest,
)
from bunkerweb_mcp.schemas.core import HealthResponse, PingResponse
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.instances import (
    InstanceCreateRequest,
    InstancesDeleteRequest,
    InstancesResponse,
    InstanceUpdateRequest,
)
from bunkerweb_mcp.schemas.jobs import JobItem, JobsResponse, RunJobsRequest
from bunkerweb_mcp.schemas.plugins import PluginsResponse
from bunkerweb_mcp.schemas.services import (
    ServiceCreateRequest,
    ServiceResponse,
    ServicesResponse,
    ServiceUpdateRequest,
)


def _make_settings() -> Settings:
    return Settings.model_validate({"BUNKERWEB_BASE_URL": "http://testserver"})


@pytest.mark.asyncio
async def test_client_uses_basic_auth_when_configured() -> None:
    settings = Settings.model_validate(
        {
            "BUNKERWEB_BASE_URL": "http://testserver",
            "BUNKERWEB_API_TOKEN": None,
            "BUNKERWEB_BASIC_USERNAME": "alice",
            "BUNKERWEB_BASIC_PASSWORD": "secret",
        }
    )
    client = BunkerWebClient(settings)
    try:
        auth_header = client.client.headers.get("Authorization")
        expected = base64.b64encode(b"alice:secret").decode("ascii")
        assert auth_header == f"Basic {expected}"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_client_prefers_bearer_over_basic() -> None:
    settings = Settings.model_validate(
        {
            "BUNKERWEB_BASE_URL": "http://testserver",
            "BUNKERWEB_API_TOKEN": "token",
            "BUNKERWEB_BASIC_USERNAME": "alice",
            "BUNKERWEB_BASIC_PASSWORD": "secret",
        }
    )
    client = BunkerWebClient(settings)
    try:
        auth_header = client.client.headers.get("Authorization")
        assert auth_header == "Bearer token"
    finally:
        await client.close()


def _json_case(
    method_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected_args: tuple[Any, ...],
    expected_kwargs: dict[str, Any],
    return_value: Any,
) -> tuple[str, tuple[Any, ...], dict[str, Any], tuple[Any, ...], dict[str, Any], Any]:
    return method_name, args, kwargs, expected_args, expected_kwargs, return_value


INSTANCE_CREATE_PAYLOAD = InstanceCreateRequest(
    hostname="edge-1",
    name="edge-1",
    port=8080,
    listen_https=True,
    https_port=8443,
    server_name="edge.local",
    method="api",
)

INSTANCE_UPDATE_PAYLOAD = InstanceUpdateRequest(
    name="Edge",
    port=8081,
    listen_https=False,
    https_port=8444,
    server_name="edge.local",
    method="api",
)

BAN_PAYLOAD = BanRequestModel(ip=IPv4Address("1.2.3.4"), exp=60, reason="api")
UNBAN_PAYLOAD = UnbanRequestModel(ip=IPv4Address("1.2.3.4"))

SERVICE_CREATE_PAYLOAD = ServiceCreateRequest(
    server_name="svc.example",
    is_draft=True,
    variables={"key": "value"},
)

SERVICE_UPDATE_PAYLOAD = ServiceUpdateRequest(
    server_name="svc-new",
    is_draft=False,
    variables={"key": "updated"},
)

SERVICE_CONFIG_PAYLOAD = {
    "SERVER_NAME": {
        "value": "integration.api.test",
        "global": False,
        "method": "api",
        "default": "",
        "template": None,
    },
    "IS_DRAFT": {
        "value": "no",
        "global": False,
        "method": "default",
        "default": "no",
        "template": None,
    },
    "USE_TEMPLATE": {
        "value": "",
        "global": True,
        "method": "default",
        "default": "",
        "template": None,
    },
}

CONFIG_CREATE_PAYLOAD = ConfigCreateRequest(
    service="svc",
    type="http",
    name="snippet",
    data="content",
)

CONFIG_UPDATE_PAYLOAD = ConfigUpdateRequest(
    new_service="svc2",
    new_type="http",
    new_name="snippet2",
    data="updated",
)

CONFIG_KEY_GLOBAL = ConfigKey(service=None, type="http", name="snippet")
CONFIG_KEY_SERVICE = ConfigKey(service="svc", type="http", name="snippet")

CACHE_DELETE_PAYLOAD = CacheFilesDeleteRequest(
    cache_files=[
        CacheFileKey.model_validate(
            {"service": "svc", "plugin": "plug", "jobName": "job", "fileName": "file"}
        )
    ]
)

RUN_JOBS_PAYLOAD = RunJobsRequest(jobs=[JobItem(plugin="plug", name="job")])

REQUEST_JSON_CASES = [
    _json_case(
        "ping",
        (),
        {},
        ("GET", "/ping"),
        {"response_model": PingResponse},
        PingResponse(status="success"),
    ),
    _json_case(
        "list_instances",
        (),
        {},
        ("GET", "/instances"),
        {"response_model": InstancesResponse},
        InstancesResponse(status="success"),
    ),
    _json_case(
        "ping_instances",
        (),
        {},
        ("GET", "/instances/ping"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "stop_instances",
        (),
        {},
        ("POST", "/instances/stop"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "get_instance",
        ("edge-1",),
        {},
        ("GET", "/instances/edge-1"),
        {"response_model": InstancesResponse},
        InstancesResponse(status="success"),
    ),
    _json_case(
        "ping_instance",
        ("edge-1",),
        {},
        ("GET", "/instances/edge-1/ping"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "stop_instance",
        ("edge-1",),
        {},
        ("POST", "/instances/edge-1/stop"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "create_instance",
        (INSTANCE_CREATE_PAYLOAD,),
        {},
        ("POST", "/instances"),
        {
            "json": INSTANCE_CREATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": InstancesResponse,
        },
        InstancesResponse(status="success"),
    ),
    _json_case(
        "update_instance",
        ("edge-1", INSTANCE_UPDATE_PAYLOAD),
        {},
        ("PATCH", "/instances/edge-1"),
        {
            "json": INSTANCE_UPDATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": InstancesResponse,
        },
        InstancesResponse(status="success"),
    ),
    _json_case(
        "delete_instances",
        (InstancesDeleteRequest(instances=["edge-1", "edge-2"]),),
        {},
        ("DELETE", "/instances"),
        {
            "json": {"instances": ["edge-1", "edge-2"]},
            "response_model": InstancesResponse,
        },
        InstancesResponse(status="success"),
    ),
    _json_case(
        "delete_instance",
        ("edge-1",),
        {},
        ("DELETE", "/instances/edge-1"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "reload_instances",
        (),
        {"test": False},
        ("POST", "/instances/reload"),
        {
            "params": {"test": "false"},
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
    _json_case(
        "reload_instance",
        ("edge-1",),
        {"test": False},
        ("POST", "/instances/edge-1/reload"),
        {
            "params": {"test": "false"},
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
    _json_case(
        "ban",
        ([BAN_PAYLOAD],),
        {},
        ("POST", "/bans"),
        {
            "json": BAN_PAYLOAD.model_dump(exclude_none=True, mode="json"),
            "response_model": BansResponse,
            "allowed_statuses": {HTTPStatus.BAD_GATEWAY},
        },
        BansResponse(status="success"),
    ),
    _json_case(
        "unban",
        ([UNBAN_PAYLOAD],),
        {},
        ("DELETE", "/bans"),
        {
            "json": UNBAN_PAYLOAD.model_dump(exclude_none=True, mode="json"),
            "response_model": BansResponse,
            "allowed_statuses": {HTTPStatus.BAD_GATEWAY},
        },
        BansResponse(status="success"),
    ),
    _json_case(
        "list_services",
        (),
        {"with_drafts": False},
        ("GET", "/services"),
        {
            "params": {"with_drafts": "false"},
            "response_model": ServicesResponse,
        },
        ServicesResponse(status="success"),
    ),
    _json_case(
        "get_service",
        ("svc",),
        {"full": True, "methods": False, "with_drafts": False},
        ("GET", "/services/svc"),
        {
            "params": {
                "full": "true",
                "methods": "false",
                "with_drafts": "false",
            },
            "response_model": ServiceResponse,
        },
        ServiceResponse(status="success", service="svc", data=SERVICE_CONFIG_PAYLOAD),
    ),
    _json_case(
        "create_service",
        (SERVICE_CREATE_PAYLOAD,),
        {},
        ("POST", "/services"),
        {
            "json": SERVICE_CREATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": ServiceResponse,
        },
        ServiceResponse(status="success"),
    ),
    _json_case(
        "update_service",
        ("svc", SERVICE_UPDATE_PAYLOAD),
        {},
        ("PATCH", "/services/svc"),
        {
            "json": SERVICE_UPDATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": ServiceResponse,
        },
        ServiceResponse(status="success"),
    ),
    _json_case(
        "delete_service",
        ("svc",),
        {},
        ("DELETE", "/services/svc"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "convert_service",
        ("svc",),
        {"convert_to": "draft"},
        ("POST", "/services/svc/convert"),
        {
            "params": {"convert_to": "draft"},
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
    _json_case(
        "read_global_config",
        (),
        {"full": True, "methods": True},
        ("GET", "/global_settings"),
        {
            "params": {"full": "true", "methods": "true"},
            "response_model": GlobalConfigResponse,
        },
        GlobalConfigResponse(status="success"),
    ),
    _json_case(
        "update_global_config",
        ({"feature": True},),
        {},
        ("PATCH", "/global_settings"),
        {
            "json": {"feature": True},
            "response_model": GlobalConfigResponse,
        },
        GlobalConfigResponse(status="success"),
    ),
    _json_case(
        "list_configs",
        (),
        {"service": "svc", "config_type": "http", "with_drafts": False, "with_data": True},
        ("GET", "/configs"),
        {
            "params": {
                "with_drafts": "false",
                "with_data": "true",
                "service": "svc",
                "type": "http",
            },
            "response_model": ConfigsResponse,
        },
        ConfigsResponse(status="success"),
    ),
    _json_case(
        "create_config",
        (CONFIG_CREATE_PAYLOAD,),
        {},
        ("POST", "/configs"),
        {
            "json": CONFIG_CREATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": ConfigResponse,
        },
        ConfigResponse(status="success"),
    ),
    _json_case(
        "delete_configs",
        (ConfigsDeleteRequest(configs=[ConfigKey(service=None, type="http", name="snippet")]),),
        {},
        ("DELETE", "/configs"),
        {
            "json": {
                "configs": [
                    {"type": "http", "name": "snippet"},
                ]
            },
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
    _json_case(
        "get_config",
        (CONFIG_KEY_GLOBAL,),
        {"with_data": True},
        ("GET", "/configs/global/http/snippet"),
        {
            "params": {"with_data": "true"},
            "response_model": ConfigResponse,
        },
        ConfigResponse(status="success"),
    ),
    _json_case(
        "update_config",
        (CONFIG_KEY_SERVICE, CONFIG_UPDATE_PAYLOAD),
        {},
        ("PATCH", "/configs/svc/http/snippet"),
        {
            "json": CONFIG_UPDATE_PAYLOAD.model_dump(exclude_none=True),
            "response_model": ConfigResponse,
        },
        ConfigResponse(status="success"),
    ),
    _json_case(
        "delete_config",
        (CONFIG_KEY_SERVICE,),
        {},
        ("DELETE", "/configs/svc/http/snippet"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "list_plugins",
        (),
        {"plugin_type": "external", "with_data": True},
        ("GET", "/plugins"),
        {
            "params": {"type": "external", "with_data": "true"},
            "response_model": PluginsResponse,
        },
        PluginsResponse(status="success"),
    ),
    _json_case(
        "delete_plugin",
        ("plugin-id",),
        {},
        ("DELETE", "/plugins/plugin-id"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "list_cache",
        (),
        {"service": "svc", "plugin": "plug", "job_name": "job", "with_data": True},
        ("GET", "/cache"),
        {
            "params": {
                "with_data": "true",
                "service": "svc",
                "plugin": "plug",
                "job_name": "job",
            },
            "response_model": CacheResponse,
        },
        CacheResponse(status="success"),
    ),
    _json_case(
        "delete_cache_files",
        (CACHE_DELETE_PAYLOAD,),
        {},
        ("DELETE", "/cache"),
        {
            "json": CACHE_DELETE_PAYLOAD.model_dump(exclude_none=True, by_alias=True),
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
    _json_case(
        "delete_cache_file",
        (),
        {"service": "svc", "plugin_id": "plug", "job_name": "job", "file_name": "file"},
        ("DELETE", "/cache/svc/plug/job/file"),
        {"response_model": ApiResponse},
        ApiResponse(status="success"),
    ),
    _json_case(
        "list_jobs",
        (),
        {},
        ("GET", "/jobs"),
        {"response_model": JobsResponse},
        JobsResponse(status="success"),
    ),
    _json_case(
        "run_jobs",
        (RUN_JOBS_PAYLOAD,),
        {},
        ("POST", "/jobs/run"),
        {
            "json": RUN_JOBS_PAYLOAD.model_dump(exclude_none=True),
            "response_model": ApiResponse,
        },
        ApiResponse(status="success"),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,args,kwargs,expected_args,expected_kwargs,return_value",
    REQUEST_JSON_CASES,
)
async def test_client_request_json_methods(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected_args: tuple[Any, ...],
    expected_kwargs: dict[str, Any],
    return_value: Any,
) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=return_value)
    monkeypatch.setattr(client, "_request_json", mock)
    method = getattr(client, method_name)
    result = await method(*args, **kwargs)
    assert result is return_value
    mock.assert_awaited_once_with(*expected_args, **expected_kwargs)
    await client.close()


@pytest.mark.asyncio
async def test_ban_requires_payload() -> None:
    settings = _make_settings()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    ) as async_client:
        client = BunkerWebClient(settings, client=async_client)
        with pytest.raises(BunkerWebError):
            await client.ban([])
        await client.close()


@pytest.mark.asyncio
async def test_list_bans_accepts_bad_gateway() -> None:
    payload = {"node-a": {"status": "success", "msg": ""}}

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as async_client:
        client = BunkerWebClient(_make_settings(), client=async_client)
        result = await client.list_bans()
        assert isinstance(result, BansResponse)
        assert result.status == "success"
        assert result.data == payload
        await client.close()


@pytest.mark.asyncio
async def test_list_instances_accepts_instances_key() -> None:
    payload = {"status": "success", "instances": [{"hostname": "edge"}]}

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as async_client:
        client = BunkerWebClient(_make_settings(), client=async_client)
        result = await client.list_instances()
        assert isinstance(result, InstancesResponse)
        assert result.data == payload["instances"]
        await client.close()


@pytest.mark.asyncio
async def test_ban_accepts_bad_gateway() -> None:
    payload = BansResponse(status="success", data={"node": {"status": "success"}})

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/bans"
        return httpx.Response(502, json=payload.model_dump(mode="json"))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as async_client:
        client = BunkerWebClient(_make_settings(), client=async_client)
        result = await client.ban([BAN_PAYLOAD])
        assert isinstance(result, BansResponse)
        assert result.status == "success"
        assert result.data == payload.data
        await client.close()


@pytest.mark.asyncio
async def test_unban_accepts_bad_gateway() -> None:
    payload = BansResponse(status="partial", data={"node": {"status": "success"}})

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/bans"
        return httpx.Response(502, json=payload.model_dump(mode="json"))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as async_client:
        client = BunkerWebClient(_make_settings(), client=async_client)
        result = await client.unban([UNBAN_PAYLOAD])
        assert isinstance(result, BansResponse)
        assert result.status == "partial"
        assert result.data == payload.data
        await client.close()


class DummyResponse:
    def __init__(
        self,
        data: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> None:
        self._data = data
        self.headers = headers or {}
        self.content = content or b""

    def json(self) -> dict[str, Any]:
        return self._data


@pytest.mark.asyncio
async def test_authenticate_builds_basic_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=DummyResponse({"status": "success"}))
    monkeypatch.setattr(client, "_request", mock)

    result = await client.authenticate(username="alice", password="secret")

    assert isinstance(result, ApiResponse)
    assert result.status == "success"
    mock.assert_awaited_once()
    await_call = mock.await_args_list[0]
    assert await_call.kwargs["json"] == {"username": "alice", "password": "secret"}
    headers = await_call.kwargs["headers"]
    assert "Authorization" in headers and headers["Authorization"].startswith("Basic ")
    await client.close()


@pytest.mark.asyncio
async def test_health_uses_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=DummyResponse({"status": "success", "details": {"db": "ok"}}))
    monkeypatch.setattr(client, "_request", mock)

    result = await client.health()

    assert isinstance(result, HealthResponse)
    mock.assert_awaited_once_with("GET", "/health")
    await client.close()


@pytest.mark.asyncio
async def test_upload_configs_forms_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=DummyResponse({"status": "success"}))
    monkeypatch.setattr(client, "_request", mock)

    files = [("config.conf", b"content")]
    result = await client.upload_configs(files=files, config_type="http", service="svc")

    assert isinstance(result, ConfigsResponse)
    mock.assert_awaited_once_with(
        "POST",
        "/configs/upload",
        files=[("files", ("config.conf", b"content"))],
        data={"type": "http", "service": "svc"},
    )
    await client.close()


@pytest.mark.asyncio
async def test_update_config_upload_accepts_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=DummyResponse({"status": "success"}))
    monkeypatch.setattr(client, "_request", mock)

    key = ConfigKey(service=None, type="http", name="snippet")
    result = await client.update_config_upload(
        key,
        file_name="config.conf",
        content=b"content",
        new_service="svc",
        new_type="http",
        new_name="renamed",
    )

    assert isinstance(result, ConfigResponse)
    mock.assert_awaited_once_with(
        "PATCH",
        "/configs/global/http/snippet/upload",
        files={"file": ("config.conf", b"content")},
        data={"new_service": "svc", "new_type": "http", "new_name": "renamed"},
    )
    await client.close()


@pytest.mark.asyncio
async def test_upload_plugins_sends_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(return_value=DummyResponse({"status": "success"}))
    monkeypatch.setattr(client, "_request", mock)

    files = [("plugin.zip", b"binary")]
    result = await client.upload_plugins(files=files, method="ui")

    assert isinstance(result, PluginsResponse)
    mock.assert_awaited_once_with(
        "POST",
        "/plugins/upload",
        files=[("files", ("plugin.zip", b"binary"))],
        data={"method": "ui"},
    )
    await client.close()


@pytest.mark.asyncio
async def test_fetch_cache_file_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(
        return_value=DummyResponse(
            {"status": "success"},
            headers={"content-type": "application/json"},
        )
    )
    monkeypatch.setattr(client, "_request", mock)

    result = await client.fetch_cache_file(
        service="svc",
        plugin_id="plug",
        job_name="job",
        file_name="file",
        download=False,
    )

    assert result == {"status": "success"}
    mock.assert_awaited_once_with(
        "GET",
        "/cache/svc/plug/job/file",
        params={"download": "false"},
    )
    await client.close()


@pytest.mark.asyncio
async def test_fetch_cache_file_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())
    mock = AsyncMock(
        return_value=DummyResponse(
            {},
            headers={"content-type": "application/octet-stream"},
            content=b"data",
        )
    )
    monkeypatch.setattr(client, "_request", mock)

    result = await client.fetch_cache_file(
        service="svc",
        plugin_id="plug",
        job_name="job",
        file_name="file",
        download=True,
    )

    assert result["filename"] == "file"
    assert result["content_type"] == "application/octet-stream"
    assert result["data_base64"] == "ZGF0YQ=="
    await client.close()


@pytest.mark.asyncio
async def test_request_converts_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())

    request = httpx.Request("GET", "http://testserver/error")
    response = httpx.Response(400, json={"message": "bad"}, request=request)

    async def fake_request(*_: Any, **__: Any) -> httpx.Response:
        return response

    monkeypatch.setattr(client.client, "request", AsyncMock(side_effect=fake_request))

    with pytest.raises(BunkerWebError) as exc:
        await client._request("GET", "/error")

    assert "bad" in str(exc.value)
    await client.close()


@pytest.mark.asyncio
async def test_request_propagates_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BunkerWebClient(_make_settings())

    request = httpx.Request("GET", "http://testserver/error")
    response = httpx.Response(502, json={"message": "fail"}, request=request)

    async def fake_request(*_: Any, **__: Any) -> httpx.Response:
        return response

    monkeypatch.setattr(client.client, "request", AsyncMock(side_effect=fake_request))

    with pytest.raises(httpx.HTTPStatusError):
        await client._request("GET", "/error")

    await client.close()


def test_extract_error_message_variants() -> None:
    client = BunkerWebClient(_make_settings())

    request = httpx.Request("GET", "http://testserver/error")
    dict_response = httpx.Response(400, json={"message": "bad"}, request=request)
    list_response = httpx.Response(400, json=["oops"], request=request)
    text_response = httpx.Response(400, content=b"plain", request=request)

    assert client._extract_error_message(dict_response) == "bad"
    assert client._extract_error_message(list_response) == "['oops']"
    assert client._extract_error_message(text_response) == "plain"
