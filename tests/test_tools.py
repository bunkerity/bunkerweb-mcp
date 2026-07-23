from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bunkerweb_mcp.exceptions import BunkerWebError, ToolExecutionError, ToolValidationError
from bunkerweb_mcp.prompt_catalog import PromptCatalog
from bunkerweb_mcp.schemas.bans import BanRequestModel, BansResponse, UnbanRequestModel
from bunkerweb_mcp.schemas.cache import CacheFileKey, CacheFilesDeleteRequest
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.configs import (
    ConfigCreateRequest,
    ConfigKey,
    ConfigsDeleteRequest,
    ConfigUpdateRequest,
)
from bunkerweb_mcp.schemas.core import AuthResponse, HealthResponse, PingResponse
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.instances import (
    InstanceCreateRequest,
    InstancesDeleteRequest,
    InstancesResponse,
    InstanceUpdateRequest,
)
from bunkerweb_mcp.schemas.jobs import JobsResponse
from bunkerweb_mcp.schemas.plugins import PluginsResponse
from bunkerweb_mcp.schemas.services import (
    ServiceCreateRequest,
    ServiceResponse,
    ServicesResponse,
)
from bunkerweb_mcp.tools import Tools

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

BANS_LIST_PAYLOAD = {
    "10-244-0-22.bunkerweb.pod.cluster.local": {
        "status": "success",
        "msg": "success",
        "data": [
            {
                "ip": "203.0.113.10",
                "reason": "tests",
                "exp": 9,
                "permanent": False,
                "service": "unknown",
                "ban_scope": "global",
                "country": "unknown",
                "date": 1765530795,
            }
        ],
    }
}


class DummyClient:
    async def ping(self) -> PingResponse:
        return PingResponse(status="success", message="pong")

    async def health(self) -> HealthResponse:
        return HealthResponse(status="success", details={"status": "ok"})

    async def list_instances(self) -> ApiResponse:
        return ApiResponse(status="success", data=[{"hostname": "test"}])

    async def reload_instances(self, *, test: bool) -> ApiResponse:
        return ApiResponse(status="success", message=f"reload:{test}")

    async def reload_instance(self, hostname: str, *, test: bool) -> ApiResponse:
        return ApiResponse(status="success", message=f"reload:{hostname}:{test}")

    async def list_bans(self) -> BansResponse:
        return BansResponse(status="success", message="success", data=BANS_LIST_PAYLOAD)

    async def ban(self, bans):  # type: ignore[no-untyped-def]
        return BansResponse(status="success")

    async def unban(self, bans):  # type: ignore[no-untyped-def]
        return BansResponse(status="success")

    async def list_services(self, *, with_drafts: bool) -> ServicesResponse:
        return ServicesResponse(status="success", data=[])

    async def get_service(
        self, service: str, *, full: bool, methods: bool, with_drafts: bool
    ) -> ServiceResponse:
        return ServiceResponse(status="success", service=service, data=SERVICE_CONFIG_PAYLOAD)

    async def delete_service(self, service: str) -> ApiResponse:
        raise RuntimeError("boom")


def test_list_descriptors_surface_prompts() -> None:
    catalog = PromptCatalog({"ping": "sample prompt"})
    tools = Tools(DummyClient(), prompt_catalog=catalog)  # type: ignore[arg-type]

    descriptors = tools.list_descriptors()

    prompt_entry = next(item for item in descriptors if item["name"] == "ping")
    assert prompt_entry["prompt"] == "sample prompt"


@pytest.mark.asyncio
async def test_ping_tool_success() -> None:
    tools = Tools(DummyClient())  # type: ignore[arg-type]
    handler = tools.get_tool("ping")
    assert handler is not None
    result = await handler({})
    assert result["message"] == "pong"


@pytest.mark.asyncio
async def test_tool_validation_error() -> None:
    tools = Tools(DummyClient())  # type: ignore[arg-type]
    handler = tools.get_tool("ban_ip")
    assert handler is not None
    with pytest.raises(ToolValidationError):
        await handler({"bans": []})


@pytest.mark.asyncio
async def test_tool_execution_error() -> None:
    tools = Tools(DummyClient())  # type: ignore[arg-type]
    handler = tools.get_tool("delete_service")
    assert handler is not None
    with pytest.raises(ToolExecutionError):
        await handler({"service": "svc"})


SIMPLE_TOOL_CASES: list[tuple[str, dict[str, Any], str, Any, tuple[Any, ...], dict[str, Any]]] = [
    (
        "list_instances",
        {},
        "list_instances",
        InstancesResponse(status="success", data=[]),
        (),
        {},
    ),
    (
        "instances_ping_all",
        {},
        "ping_instances",
        ApiResponse(status="success"),
        (),
        {},
    ),
    (
        "instances_stop_all",
        {},
        "stop_instances",
        ApiResponse(status="success"),
        (),
        {},
    ),
    (
        "instance_get",
        {"hostname": "edge"},
        "get_instance",
        InstancesResponse(status="success", data=[]),
        ("edge",),
        {},
    ),
    (
        "instance_ping",
        {"hostname": "edge"},
        "ping_instance",
        ApiResponse(status="success"),
        ("edge",),
        {},
    ),
    (
        "instance_stop",
        {"hostname": "edge"},
        "stop_instance",
        ApiResponse(status="success"),
        ("edge",),
        {},
    ),
    (
        "instance_delete",
        {"hostname": "edge"},
        "delete_instance",
        ApiResponse(status="success"),
        ("edge",),
        {},
    ),
    (
        "reload_instances",
        {"test": False},
        "reload_instances",
        ApiResponse(status="success"),
        (),
        {"test": False},
    ),
    (
        "reload_instance",
        {"hostname": "edge", "test": False},
        "reload_instance",
        ApiResponse(status="success"),
        (),
        {"hostname": "edge", "test": False},
    ),
    (
        "list_bans",
        {},
        "list_bans",
        BansResponse(status="success", message="success", data=BANS_LIST_PAYLOAD),
        (),
        {},
    ),
    (
        "list_services",
        {},
        "list_services",
        ServicesResponse(status="success", data=[]),
        (),
        {"with_drafts": True},
    ),
    (
        "global_config_read",
        {},
        "read_global_config",
        GlobalConfigResponse(status="success", data={}),
        (),
        {"full": False, "methods": False},
    ),
    (
        "cache_list",
        {"plugin": "plug", "job_name": "job", "service": None, "with_data": True},
        "list_cache",
        ApiResponse(status="success", data=[]),
        (),
        {"service": None, "plugin": "plug", "job_name": "job", "with_data": True},
    ),
    (
        "jobs_list",
        {},
        "list_jobs",
        JobsResponse(status="success", data={}),
        (),
        {},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,payload,attr,response,expected_args,expected_kwargs", SIMPLE_TOOL_CASES
)
async def test_tools_delegate_simple_calls(
    tool_name: str,
    payload: dict[str, Any],
    attr: str,
    response: Any,
    expected_args: tuple[Any, ...],
    expected_kwargs: dict[str, Any],
) -> None:
    client = SimpleNamespace()
    mock = AsyncMock(return_value=response)
    setattr(client, attr, mock)
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool(tool_name)
    assert handler is not None

    result = await handler(payload)

    assert result["status"] == response.status
    call = mock.await_args_list[0]
    assert call.args == expected_args
    assert call.kwargs == expected_kwargs


@pytest.mark.asyncio
async def test_authenticate_tool_success() -> None:
    client = SimpleNamespace(authenticate=AsyncMock(return_value=AuthResponse(token="biscuit")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("authenticate")
    assert handler is not None

    result = await handler(
        {"username": "alice", "password": "secret", "payload": {"scope": "admin"}}
    )

    assert result["token"] == "biscuit"
    call = client.authenticate.await_args_list[0]
    assert call.kwargs == {
        "username": "alice",
        "password": "secret",
        "payload": {"scope": "admin"},
    }


@pytest.mark.asyncio
async def test_instance_create_tool_builds_model() -> None:
    client = SimpleNamespace(
        create_instance=AsyncMock(
            return_value=InstancesResponse(status="success", data=[{"hostname": "edge"}])
        )
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("instance_create")
    assert handler is not None

    result = await handler(
        {
            "hostname": "edge",
            "name": "edge",
            "port": 8080,
            "listen_https": True,
            "https_port": 8443,
        }
    )

    assert result["status"] == "success"
    payload = client.create_instance.await_args_list[0].args[0]
    assert isinstance(payload, InstanceCreateRequest)
    assert payload.hostname == "edge"
    assert payload.listen_https is True


@pytest.mark.asyncio
async def test_service_update_tool_filters_none() -> None:
    client = SimpleNamespace(
        update_service=AsyncMock(
            return_value=ServiceResponse(
                status="success", service="svc", data=SERVICE_CONFIG_PAYLOAD
            )
        )
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("update_service")
    assert handler is not None

    await handler({"service": "svc", "server_name": "new"})

    call = client.update_service.await_args_list[0]
    assert call.args[0] == "svc"
    payload = call.args[1]
    assert payload.server_name == "new"
    assert payload.is_draft is None
    assert payload.variables is None


@pytest.mark.asyncio
async def test_service_create_tool_builds_model() -> None:
    client = SimpleNamespace(
        create_service=AsyncMock(
            return_value=ServiceResponse(
                status="success", service="integration.api.test", data=SERVICE_CONFIG_PAYLOAD
            )
        )
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("create_service")
    assert handler is not None

    result = await handler({"server_name": "integration.api.test", "is_draft": False})

    assert result["status"] == "success"
    call = client.create_service.await_args_list[0]
    payload = call.args[0]
    assert payload.server_name == "integration.api.test"
    assert payload.is_draft is False


@pytest.mark.asyncio
async def test_service_convert_tool_delegates() -> None:
    client = SimpleNamespace(
        convert_service=AsyncMock(return_value=ApiResponse(status="success", message="convert"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("convert_service")
    assert handler is not None

    result = await handler({"service": "svc", "convert_to": "online"})

    assert result["status"] == "success"
    call = client.convert_service.await_args_list[0]
    assert call.args[0] == "svc"
    assert call.kwargs == {"convert_to": "online"}


@pytest.mark.asyncio
async def test_configs_delete_bulk_builds_request() -> None:
    client = SimpleNamespace(
        delete_configs=AsyncMock(return_value=ApiResponse(status="success", message="done"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("configs_delete_bulk")
    assert handler is not None

    payload: dict[str, Any] = {
        "configs": [
            {"service": None, "type": "http", "name": "a"},
            {"service": "svc", "type": "stream", "name": "b"},
        ]
    }
    result = await handler(payload)

    assert result["message"] == "done"
    request_model = client.delete_configs.await_args_list[0].args[0]
    assert isinstance(request_model, ConfigsDeleteRequest)
    assert len(request_model.configs) == 2
    assert request_model.configs[0].service is None
    assert request_model.configs[1].service == "svc"


@pytest.mark.asyncio
async def test_cache_fetch_file_defaults_service() -> None:
    client = SimpleNamespace(
        fetch_cache_file=AsyncMock(return_value={"status": "success", "data": "ok"})
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("cache_fetch_file")
    assert handler is not None

    result = await handler(
        {"plugin": "plug", "job_name": "job", "file_name": "file", "download": False}
    )

    assert result == {"status": "success", "data": "ok"}
    call = client.fetch_cache_file.await_args_list[0]
    assert call.kwargs["service"] == "global"
    assert call.kwargs["plugin_id"] == "plug"


@pytest.mark.asyncio
async def test_tool_wraps_bunkerweb_error() -> None:
    client = SimpleNamespace(
        delete_service=AsyncMock(side_effect=BunkerWebError("upstream failed"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("delete_service")
    assert handler is not None

    with pytest.raises(ToolExecutionError):
        await handler({"service": "svc"})


@pytest.mark.asyncio
async def test_instance_update_tool_excludes_hostname() -> None:
    client = SimpleNamespace(
        update_instance=AsyncMock(return_value=InstancesResponse(status="success", data=[]))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("instance_update")
    assert handler is not None

    await handler({"hostname": "edge", "port": 8081})

    call = client.update_instance.await_args_list[0]
    assert call.args[0] == "edge"
    payload = call.args[1]
    assert isinstance(payload, InstanceUpdateRequest)
    assert payload.port == 8081


@pytest.mark.asyncio
async def test_instances_delete_tool_builds_request() -> None:
    client = SimpleNamespace(
        delete_instances=AsyncMock(return_value=InstancesResponse(status="success", data=[]))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("instances_delete_bulk")
    assert handler is not None

    await handler({"instances": ["a", "b"]})

    request = client.delete_instances.await_args_list[0].args[0]
    assert isinstance(request, InstancesDeleteRequest)
    assert request.instances == ["a", "b"]


@pytest.mark.asyncio
async def test_ban_tool_converts_models() -> None:
    client = SimpleNamespace(ban=AsyncMock(return_value=BansResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("ban_ip")
    assert handler is not None

    await handler({"bans": [{"ip": "1.2.3.4"}]})

    ban_models = client.ban.await_args_list[0].args[0]
    assert isinstance(ban_models[0], BanRequestModel)


@pytest.mark.asyncio
async def test_unban_tool_converts_models() -> None:
    client = SimpleNamespace(unban=AsyncMock(return_value=BansResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("unban_ip")
    assert handler is not None

    await handler({"bans": [{"ip": "1.2.3.4"}]})

    unban_models = client.unban.await_args_list[0].args[0]
    assert isinstance(unban_models[0], UnbanRequestModel)


@pytest.mark.asyncio
async def test_get_service_tool_defaults() -> None:
    client = SimpleNamespace(
        get_service=AsyncMock(
            return_value=ServiceResponse(
                status="success", service="svc", data=SERVICE_CONFIG_PAYLOAD
            )
        )
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("get_service")
    assert handler is not None

    await handler({"service": "svc"})

    call = client.get_service.await_args_list[0]
    assert call.args[0] == "svc"
    assert call.kwargs == {"full": False, "methods": True, "with_drafts": True}


@pytest.mark.asyncio
async def test_create_service_tool_builds_model() -> None:
    client = SimpleNamespace(
        create_service=AsyncMock(
            return_value=ServiceResponse(
                status="success", service="svc", data=SERVICE_CONFIG_PAYLOAD
            )
        )
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("create_service")
    assert handler is not None

    await handler({"server_name": "svc", "is_draft": True})

    payload = client.create_service.await_args_list[0].args[0]
    assert isinstance(payload, ServiceCreateRequest)
    assert payload.server_name == "svc"
    assert payload.is_draft is True


@pytest.mark.asyncio
async def test_convert_service_tool_passes_params() -> None:
    client = SimpleNamespace(convert_service=AsyncMock(return_value=ApiResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("convert_service")
    assert handler is not None

    await handler({"service": "svc", "convert_to": "draft"})

    call = client.convert_service.await_args_list[0]
    assert call.args[0] == "svc"
    assert call.kwargs == {"convert_to": "draft"}


@pytest.mark.asyncio
async def test_global_config_update_tool() -> None:
    client = SimpleNamespace(
        update_global_config=AsyncMock(return_value=GlobalConfigResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("global_config_update")
    assert handler is not None

    await handler({"config": {"feature": True}})

    payload = client.update_global_config.await_args_list[0].args[0]
    assert payload == {"feature": True}


@pytest.mark.asyncio
async def test_configs_list_tool_passes_filters() -> None:
    client = SimpleNamespace(
        list_configs=AsyncMock(return_value=ApiResponse(status="success", data=[]))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("configs_list")
    assert handler is not None

    await handler({"service": "svc", "type": "http", "with_data": True, "with_drafts": False})

    call = client.list_configs.await_args_list[0]
    assert call.kwargs == {
        "service": "svc",
        "config_type": "http",
        "with_drafts": False,
        "with_data": True,
    }


@pytest.mark.asyncio
async def test_config_get_tool_sets_with_data() -> None:
    client = SimpleNamespace(
        get_config=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("config_get")
    assert handler is not None

    await handler({"service": None, "type": "http", "name": "snippet"})

    call = client.get_config.await_args_list[0]
    key = call.args[0]
    assert isinstance(key, ConfigKey)
    assert key.service is None
    assert call.kwargs == {"with_data": True}


@pytest.mark.asyncio
async def test_config_create_tool_builds_model() -> None:
    client = SimpleNamespace(
        create_config=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("config_create")
    assert handler is not None

    await handler(
        {
            "service": "svc",
            "type": "http",
            "name": "snippet",
            "data": "value",
            "is_draft": True,
        }
    )

    payload = client.create_config.await_args_list[0].args[0]
    assert isinstance(payload, ConfigCreateRequest)
    assert payload.data == "value"
    assert payload.is_draft is True


@pytest.mark.asyncio
async def test_config_update_tool_builds_models() -> None:
    client = SimpleNamespace(
        update_config=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("config_update")
    assert handler is not None

    await handler(
        {
            "service": "svc",
            "type": "http",
            "name": "old",
            "new_name": "new",
            "data": "content",
            "is_draft": True,
        }
    )

    call = client.update_config.await_args_list[0]
    key = call.args[0]
    payload = call.args[1]
    assert isinstance(key, ConfigKey)
    assert isinstance(payload, ConfigUpdateRequest)
    assert payload.service == "svc"
    assert payload.name == "new"
    assert payload.is_draft is True


@pytest.mark.asyncio
async def test_config_delete_tool_builds_key() -> None:
    client = SimpleNamespace(
        delete_config=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("config_delete")
    assert handler is not None

    await handler({"service": "svc", "type": "http", "name": "snippet"})

    key = client.delete_config.await_args_list[0].args[0]
    assert isinstance(key, ConfigKey)
    assert key.name == "snippet"


@pytest.mark.asyncio
async def test_configs_upload_tool_decodes_files() -> None:
    client = SimpleNamespace(
        upload_configs=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("configs_upload")
    assert handler is not None

    await handler(
        {
            "config_type": "http",
            "service": "svc",
            "files": [
                {"filename": "file.conf", "content_base64": "Y29udGVudA=="},
            ],
            "is_draft": True,
        }
    )

    files = client.upload_configs.await_args_list[0].kwargs["files"]
    assert files == [("file.conf", b"content")]
    assert client.upload_configs.await_args_list[0].kwargs["is_draft"] is True


@pytest.mark.asyncio
async def test_config_upload_update_tool_handles_rename() -> None:
    client = SimpleNamespace(
        update_config_upload=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("config_upload_update")
    assert handler is not None

    await handler(
        {
            "service": None,
            "type": "http",
            "name": "snippet",
            "file": {"filename": "conf", "content_base64": "YQ=="},
            "new_service": "svc",
            "new_is_draft": True,
        }
    )

    call = client.update_config_upload.await_args_list[0]
    key = call.args[0]
    assert isinstance(key, ConfigKey)
    assert key.service is None
    assert call.kwargs["file_name"] == "conf"
    assert call.kwargs["content"] == b"a"
    assert call.kwargs["new_service"] == "svc"
    assert call.kwargs["new_is_draft"] is True


@pytest.mark.asyncio
async def test_plugins_list_tool_passes_filters() -> None:
    client = SimpleNamespace(
        list_plugins=AsyncMock(return_value=PluginsResponse(status="success", data=[]))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("plugins_list")
    assert handler is not None

    await handler({"type": "external", "with_data": True})

    call = client.list_plugins.await_args_list[0]
    assert call.kwargs == {"plugin_type": "external", "with_data": True}


@pytest.mark.asyncio
async def test_plugins_upload_tool_transforms_files() -> None:
    client = SimpleNamespace(
        upload_plugins=AsyncMock(return_value=PluginsResponse(status="success", data=[]))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("plugins_upload")
    assert handler is not None

    await handler(
        {
            "method": "api",
            "files": [
                {"filename": "plugin.zip", "content_base64": "Ymlu"},
            ],
        }
    )

    files = client.upload_plugins.await_args_list[0].kwargs["files"]
    assert files == [("plugin.zip", b"bin")]


@pytest.mark.asyncio
async def test_plugin_delete_tool_calls_client() -> None:
    client = SimpleNamespace(delete_plugin=AsyncMock(return_value=ApiResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("plugin_delete")
    assert handler is not None

    await handler({"plugin_id": "plug"})

    call = client.delete_plugin.await_args_list[0]
    assert call.args[0] == "plug"


@pytest.mark.asyncio
async def test_cache_delete_bulk_tool_builds_models() -> None:
    client = SimpleNamespace(
        delete_cache_files=AsyncMock(return_value=ApiResponse(status="success"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("cache_delete_bulk")
    assert handler is not None

    await handler(
        {
            "files": [
                {
                    "service": "svc",
                    "plugin": "plug",
                    "job_name": "job",
                    "file_name": "file",
                }
            ]
        }
    )

    request = client.delete_cache_files.await_args_list[0].args[0]
    assert isinstance(request, CacheFilesDeleteRequest)
    assert isinstance(request.cache_files[0], CacheFileKey)


@pytest.mark.asyncio
async def test_cache_delete_file_defaults_service() -> None:
    client = SimpleNamespace(
        delete_cache_file=AsyncMock(return_value=ApiResponse(status="success"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("cache_delete_file")
    assert handler is not None

    await handler({"service": None, "plugin": "plug", "job_name": "job", "file_name": "file"})

    call = client.delete_cache_file.await_args_list[0]
    assert call.kwargs["service"] == "global"


@pytest.mark.asyncio
async def test_jobs_run_tool_builds_models() -> None:
    client = SimpleNamespace(run_jobs=AsyncMock(return_value=ApiResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("jobs_run")
    assert handler is not None

    await handler({"jobs": [{"plugin": "plug", "name": "job"}]})

    request = client.run_jobs.await_args_list[0].args[0]
    assert request.jobs[0].plugin == "plug"
