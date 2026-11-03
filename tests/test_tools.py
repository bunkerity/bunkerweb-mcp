import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.exceptions import BunkerWebError, ToolExecutionError, ToolValidationError
from bunkerweb_mcp.prompt_catalog import PromptCatalog, load_catalog
from bunkerweb_mcp.schemas.bans import BanRequestModel, BansResponse, UnbanRequestModel
from bunkerweb_mcp.schemas.cache import CacheFileKey, CacheFilesDeleteRequest
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.configs import (
    ConfigCreateRequest,
    ConfigKey,
    ConfigsDeleteRequest,
    ConfigUpdateRequest,
)
from bunkerweb_mcp.schemas.core import AuthResponse, PingResponse
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
from bunkerweb_mcp.tools.params import ReloadInstancesParams
from bunkerweb_mcp.tools.registry import (
    SEARCH_TOOL_DESCRIPTION,
    TOOL_DESCRIPTIONS,
    TOOL_EFFECTS,
    ToolEffect,
    effect_for,
)

ALL_DESCRIPTIONS = {**TOOL_DESCRIPTIONS, "search_bunkerweb_docs": SEARCH_TOOL_DESCRIPTION}

SAVED_PHRASE = (
    "Saved to the database; the scheduler applies it later; this tool cannot confirm it is live."
)
DIRECT_PHRASE = "Acts on the instances immediately."
QUEUED_PHRASE = "Queued for the scheduler; this tool cannot confirm it ran."

CREATE_API_TOKEN_DESCRIPTION = (
    "Create a BunkerWeb API token (Biscuit) for use outside this server; returns only the "
    "token, a live credential to keep secret. Give username and password, or omit both to use "
    "the server's credentials. Needs an API user; lifetime is BunkerWeb's "
    "API_BISCUIT_TTL_SECONDS. Redaction may mask it."
)

# Route paths below are relative to bunkerweb-dev/src/api/app/routers/.
WRITE_TIMING = {
    "create_service": SAVED_PHRASE,
    "update_service": SAVED_PHRASE,
    "delete_service": SAVED_PHRASE,
    "update_global_config": SAVED_PHRASE,
    "create_config": SAVED_PHRASE,
    "update_config": SAVED_PHRASE,
    "delete_configs": SAVED_PHRASE,
    "create_configs_from_files": SAVED_PHRASE,
    "update_config_from_file": SAVED_PHRASE,
    "stop_instances": DIRECT_PHRASE,
    "reload_instances": DIRECT_PHRASE,
    "run_jobs": QUEUED_PHRASE,  # jobs.py:18-31 sets plugin change flags.
    "ban_ips": DIRECT_PHRASE,  # bans.py:64 calls /ban on the instances.
    "unban_ips": DIRECT_PHRASE,  # bans.py:235 calls /unban on the instances.
    "delete_cache_files": QUEUED_PHRASE,  # cache.py:147-160 deletes rows and sets flags.
    "install_plugins": SAVED_PHRASE,  # plugins.py:227,280 stores plugin data in the DB.
    "uninstall_plugin": SAVED_PHRASE,  # plugins.py:134 deletes from the DB with changes=True.
    "create_instance": SAVED_PHRASE,  # instances.py:162 adds a DB instance record.
    "update_instance": SAVED_PHRASE,  # instances.py:225 updates DB instance fields.
    "delete_instances": SAVED_PHRASE,  # instances.py:299 deletes DB instance records.
}


def test_write_descriptions_state_timing() -> None:
    phrases = (SAVED_PHRASE, DIRECT_PHRASE, QUEUED_PHRASE)
    assert set(WRITE_TIMING) == {
        name for name, effect in TOOL_EFFECTS.items() if not effect.read_only
    } - {"create_api_token"}
    for name, description in ALL_DESCRIPTIONS.items():
        if name in WRITE_TIMING:
            assert WRITE_TIMING[name] in description, name
            assert sum(description.count(phrase) for phrase in phrases) == 1, name
        else:
            assert not any(phrase in description for phrase in phrases), name
    assert TOOL_DESCRIPTIONS["create_api_token"] == CREATE_API_TOKEN_DESCRIPTION


def test_create_api_token_claims_no_expiry_field() -> None:
    """POST /auth returns only the token (schemas/core.py AuthResponse); the lifetime is a server setting."""
    description = TOOL_DESCRIPTIONS["create_api_token"]
    assert "expires_at" not in description
    assert "API_BISCUIT_TTL_SECONDS" in description
    assert "credential" in description


def test_redaction_names_are_registered_tools() -> None:
    from bunkerweb_mcp.redaction import SETTINGS_WRITE_FIELDS

    assert set(SETTINGS_WRITE_FIELDS) <= set(TOOL_DESCRIPTIONS)


def test_cache_ttl_keys_are_registered_tools() -> None:
    from bunkerweb_mcp.cache import CACHE_TTL

    assert set(CACHE_TTL) <= set(TOOL_DESCRIPTIONS)


def test_prompt_keys_are_registered_tools() -> None:
    prompts = load_catalog(Settings()).descriptors()
    assert set(prompts) <= set(TOOL_DESCRIPTIONS) | {"search_bunkerweb_docs"}


def test_descriptions_are_short() -> None:
    for name, description in ALL_DESCRIPTIONS.items():
        assert len(description) <= 300, name


def test_reload_test_is_not_described_as_dry_run() -> None:
    description = ReloadInstancesParams.model_fields["test"].description
    assert description is not None
    assert "validation-only" not in description
    assert "still reloads" in description


def test_prompts_do_not_claim_automatic_application() -> None:
    phrase = "BunkerWeb will automatically apply the changes."
    prompts = load_catalog(Settings()).descriptors()
    assert prompts
    for name, prompt in prompts.items():
        assert phrase not in prompt, name


def test_every_tool_has_an_effect() -> None:
    names = set(TOOL_DESCRIPTIONS) | {"search_bunkerweb_docs"}
    assert names == set(TOOL_EFFECTS)


def test_unknown_tool_is_treated_as_destructive_write() -> None:
    assert effect_for("not_a_tool") == ToolEffect(read_only=False, destructive=True)


def test_reload_is_a_destructive_write() -> None:
    assert TOOL_EFFECTS["reload_instances"] == ToolEffect(read_only=False, destructive=True)


def test_descriptors_carry_effects() -> None:
    by_name = {d["name"]: d for d in Tools(SimpleNamespace()).list_descriptors()}  # type: ignore[arg-type]
    assert by_name["get_service"]["read_only"] is True
    assert by_name["delete_service"]["destructive"] is True


def test_read_only_tools_drop_writes() -> None:
    tools = Tools(SimpleNamespace(), read_only=True)  # type: ignore[arg-type]
    assert tools.get_tool("get_service") is not None
    assert tools.get_tool("update_service") is None
    assert tools.get_tool("create_api_token") is None
    assert all(effect_for(d["name"]).read_only for d in tools.list_descriptors())


def test_read_only_tools_drop_unclassified_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(TOOL_EFFECTS, "get_service")
    tools = Tools(SimpleNamespace(), read_only=True)  # type: ignore[arg-type]
    assert tools.get_tool("get_service") is None
    assert tools.get_tool("list_services") is not None


def test_read_descriptions_only_name_writes_conditionally() -> None:
    """In read-only mode a read must not direct agents to a write tool as if it existed."""
    writes = {name for name, effect in TOOL_EFFECTS.items() if not effect.read_only}
    for name, description in ALL_DESCRIPTIONS.items():
        if not effect_for(name).read_only:
            continue
        for write in writes:
            if re.search(rf"\b{re.escape(write)}\b", description):
                assert re.search(rf"\b{re.escape(write)} when writes are enabled", description), (
                    name,
                    write,
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
    catalog = PromptCatalog({"ping_api": "sample prompt"})
    tools = Tools(DummyClient(), prompt_catalog=catalog)  # type: ignore[arg-type]

    descriptors = tools.list_descriptors()

    prompt_entry = next(item for item in descriptors if item["name"] == "ping_api")
    assert prompt_entry["prompt"] == "sample prompt"


@pytest.mark.asyncio
async def test_ping_tool_success() -> None:
    tools = Tools(DummyClient())  # type: ignore[arg-type]
    handler = tools.get_tool("ping_api")
    assert handler is not None
    result = await handler({})
    assert result["message"] == "pong"


@pytest.mark.asyncio
async def test_tool_validation_error() -> None:
    tools = Tools(DummyClient())  # type: ignore[arg-type]
    handler = tools.get_tool("ban_ips")
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
        "ping_instances",
        {},
        "ping_instances",
        ApiResponse(status="success"),
        (),
        {},
    ),
    (
        "stop_instances",
        {"all": True},
        "stop_instances",
        ApiResponse(status="success"),
        (),
        {},
    ),
    (
        "get_instance",
        {"hostname": "edge"},
        "get_instance",
        InstancesResponse(status="success", data=[]),
        ("edge",),
        {},
    ),
    (
        "ping_instances",
        {"hostname": "edge"},
        "ping_instance",
        ApiResponse(status="success"),
        ("edge",),
        {},
    ),
    (
        "stop_instances",
        {"hostname": "edge"},
        "stop_instance",
        ApiResponse(status="success"),
        ("edge",),
        {},
    ),
    (
        "reload_instances",
        {"all": True, "test": False},
        "reload_instances",
        ApiResponse(status="success"),
        (),
        {"test": False},
    ),
    (
        "reload_instances",
        {"hostname": "edge", "test": False},
        "reload_instance",
        ApiResponse(status="success"),
        ("edge",),
        {"test": False},
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
        "get_global_config",
        {},
        "read_global_config",
        GlobalConfigResponse(status="success", data={}),
        (),
        {"full": False, "methods": False},
    ),
    (
        "list_cache_files",
        {"plugin": "plug", "job_name": "job", "service": None, "with_data": True},
        "list_cache",
        ApiResponse(status="success", data=[]),
        (),
        {"service": None, "plugin": "plug", "job_name": "job", "with_data": True},
    ),
    (
        "list_jobs",
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
    handler = tools.get_tool("create_api_token")
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
    handler = tools.get_tool("create_instance")
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
        base_url="http://tools-update",
        get_openapi_version=AsyncMock(return_value="1.6.17"),
        read_global_config=AsyncMock(return_value=GlobalConfigResponse(data={"MULTISITE": "yes"})),
        get_service=AsyncMock(return_value=ServiceResponse(data=SERVICE_CONFIG_PAYLOAD)),
        list_plugins=AsyncMock(return_value=PluginsResponse(data=[])),
        update_service=AsyncMock(
            return_value=ServiceResponse(
                status="success", service="svc", data=SERVICE_CONFIG_PAYLOAD
            )
        ),
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
async def test_configs_delete_bulk_builds_request() -> None:
    client = SimpleNamespace(
        delete_configs=AsyncMock(return_value=ApiResponse(status="success", message="done"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("delete_configs")
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
    handler = tools.get_tool("get_cache_file")
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
    handler = tools.get_tool("update_instance")
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
    handler = tools.get_tool("delete_instances")
    assert handler is not None

    await handler({"instances": ["a", "b"]})

    request = client.delete_instances.await_args_list[0].args[0]
    assert isinstance(request, InstancesDeleteRequest)
    assert request.instances == ["a", "b"]


@pytest.mark.asyncio
async def test_ban_tool_converts_models() -> None:
    client = SimpleNamespace(ban=AsyncMock(return_value=BansResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("ban_ips")
    assert handler is not None

    await handler({"bans": [{"ip": "1.2.3.4"}]})

    ban_models = client.ban.await_args_list[0].args[0]
    assert isinstance(ban_models[0], BanRequestModel)


@pytest.mark.asyncio
async def test_unban_tool_converts_models() -> None:
    client = SimpleNamespace(unban=AsyncMock(return_value=BansResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("unban_ips")
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
async def test_global_config_update_tool() -> None:
    client = SimpleNamespace(
        update_global_config=AsyncMock(return_value=GlobalConfigResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("update_global_config")
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
    handler = tools.get_tool("list_configs")
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
    handler = tools.get_tool("get_config")
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
    handler = tools.get_tool("create_config")
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
    handler = tools.get_tool("update_config")
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
        delete_configs=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("delete_configs")
    assert handler is not None

    await handler({"configs": [{"service": "svc", "type": "http", "name": "snippet"}]})

    request = client.delete_configs.await_args_list[0].args[0]
    assert isinstance(request, ConfigsDeleteRequest)
    key = request.configs[0]
    assert isinstance(key, ConfigKey)
    assert key.name == "snippet"


@pytest.mark.asyncio
async def test_configs_upload_tool_decodes_files() -> None:
    client = SimpleNamespace(
        upload_configs=AsyncMock(return_value=ApiResponse(status="success", data={}))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("create_configs_from_files")
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
    handler = tools.get_tool("update_config_from_file")
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
    handler = tools.get_tool("list_plugins")
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
    handler = tools.get_tool("install_plugins")
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
    handler = tools.get_tool("uninstall_plugin")
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
    handler = tools.get_tool("delete_cache_files")
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
async def test_cache_delete_without_service_sends_global_key() -> None:
    client = SimpleNamespace(
        delete_cache_files=AsyncMock(return_value=ApiResponse(status="success"))
    )
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("delete_cache_files")
    assert handler is not None

    await handler(
        {"files": [{"service": None, "plugin": "plug", "job_name": "job", "file_name": "f"}]}
    )

    key = client.delete_cache_files.await_args_list[0].args[0].cache_files[0]
    assert key.service is None  # the API reads a missing service as "global"


@pytest.mark.asyncio
async def test_jobs_run_tool_builds_models() -> None:
    client = SimpleNamespace(run_jobs=AsyncMock(return_value=ApiResponse(status="success")))
    tools = Tools(client)  # type: ignore[arg-type]
    handler = tools.get_tool("run_jobs")
    assert handler is not None

    await handler({"jobs": [{"plugin": "plug", "name": "job"}]})

    request = client.run_jobs.await_args_list[0].args[0]
    assert request.jobs[0].plugin == "plug"


EXPECTED_TOOLS = {
    "create_api_token",
    "ping_api",
    "diagnose_bunkerweb",
    "list_instances",
    "get_instance",
    "create_instance",
    "update_instance",
    "delete_instances",
    "ping_instances",
    "stop_instances",
    "reload_instances",
    "list_bans",
    "ban_ips",
    "unban_ips",
    "list_services",
    "get_service",
    "create_service",
    "update_service",
    "delete_service",
    "get_global_config",
    "update_global_config",
    "list_configs",
    "get_config",
    "create_config",
    "create_configs_from_files",
    "update_config",
    "update_config_from_file",
    "delete_configs",
    "list_plugins",
    "install_plugins",
    "uninstall_plugin",
    "list_cache_files",
    "get_cache_file",
    "delete_cache_files",
    "list_jobs",
    "run_jobs",
}
REMOVED_TOOLS = {
    "authenticate",
    "ping",
    "health",
    "diagnose",
    "instance_get",
    "instance_create",
    "instance_update",
    "instance_delete",
    "instances_delete_bulk",
    "instance_ping",
    "instances_ping_all",
    "instance_stop",
    "instances_stop_all",
    "reload_instance",
    "ban_ip",
    "unban_ip",
    "convert_service",
    "global_config_read",
    "global_config_update",
    "configs_list",
    "config_get",
    "config_create",
    "configs_upload",
    "config_update",
    "config_upload_update",
    "config_delete",
    "configs_delete_bulk",
    "plugins_list",
    "plugins_upload",
    "plugin_delete",
    "cache_list",
    "cache_fetch_file",
    "cache_delete_file",
    "cache_delete_bulk",
    "jobs_list",
    "jobs_run",
    "logs_list",
    "logs_read",
    "ping_instance",
    "stop_instance",
    "delete_instance",
    "delete_config",
    "delete_cache_file",
}


def test_registered_tool_names(tmp_path: Path) -> None:
    descriptors = Tools(SimpleNamespace(), logs_path=tmp_path).list_descriptors()  # type: ignore[arg-type]
    names = {d["name"] for d in descriptors}
    assert names == EXPECTED_TOOLS | {"list_logs", "read_log"}
    assert not names & REMOVED_TOOLS
    without_logs = {d["name"] for d in Tools(SimpleNamespace()).list_descriptors()}  # type: ignore[arg-type]
    assert without_logs == EXPECTED_TOOLS


@pytest.mark.parametrize("tool", ["stop_instances", "reload_instances"])
@pytest.mark.parametrize(
    "payload",
    [{}, {"all": False}, {"hostname": "bw-1", "all": True}, {"hostname": ""}],
)
@pytest.mark.asyncio
async def test_instance_target_needs_exactly_one(tool: str, payload: dict[str, Any]) -> None:
    client = AsyncMock()
    handler = Tools(client).get_tool(tool)
    assert handler is not None
    with pytest.raises(ToolValidationError, match="hostname"):
        await handler(payload)
    assert client.method_calls == []


@pytest.mark.asyncio
async def test_reload_with_only_test_flag_names_both_targets() -> None:
    client = AsyncMock()
    handler = Tools(client).get_tool("reload_instances")
    assert handler is not None
    with pytest.raises(ToolValidationError, match=r"hostname or all"):
        await handler({"test": False})
    assert client.method_calls == []


@pytest.mark.asyncio
async def test_ping_instances_routes_by_hostname() -> None:
    client = SimpleNamespace(
        ping_instance=AsyncMock(return_value=ApiResponse(status="success", message="one")),
        ping_instances=AsyncMock(return_value=ApiResponse(status="success", message="all")),
    )
    handler = Tools(client).get_tool("ping_instances")  # type: ignore[arg-type]
    assert handler is not None
    assert (await handler({"hostname": "bw-1"}))["message"] == "one"
    client.ping_instance.assert_awaited_once_with("bw-1")
    client.ping_instances.assert_not_awaited()
    assert (await handler({}))["message"] == "all"
    client.ping_instances.assert_awaited_once_with()
    with pytest.raises(ToolValidationError):
        await handler({"hostname": ""})


@pytest.mark.asyncio
async def test_stop_and_reload_route_by_target() -> None:
    ok = ApiResponse(status="success")
    client = SimpleNamespace(
        stop_instance=AsyncMock(return_value=ok),
        stop_instances=AsyncMock(return_value=ok),
        reload_instance=AsyncMock(return_value=ok),
        reload_instances=AsyncMock(return_value=ok),
    )
    tools = Tools(client)  # type: ignore[arg-type]
    stop = tools.get_tool("stop_instances")
    reload = tools.get_tool("reload_instances")
    assert stop is not None and reload is not None

    await stop({"hostname": "bw-1"})
    client.stop_instance.assert_awaited_once_with("bw-1")
    client.stop_instances.assert_not_awaited()
    await stop({"all": True})
    client.stop_instances.assert_awaited_once_with()

    await reload({"hostname": "bw-1", "test": False})
    client.reload_instance.assert_awaited_once_with("bw-1", test=False)
    client.reload_instances.assert_not_awaited()
    await reload({"all": True})
    client.reload_instances.assert_awaited_once_with(test=True)


@pytest.mark.asyncio
async def test_single_item_delete_uses_bulk_endpoint() -> None:
    ok = ApiResponse(status="success")
    client = SimpleNamespace(
        delete_instances=AsyncMock(return_value=ok),
        delete_configs=AsyncMock(return_value=ok),
        delete_cache_files=AsyncMock(return_value=ok),
    )
    tools = Tools(client)  # type: ignore[arg-type]
    delete_instances = tools.get_tool("delete_instances")
    delete_configs = tools.get_tool("delete_configs")
    delete_cache_files = tools.get_tool("delete_cache_files")
    assert delete_instances and delete_configs and delete_cache_files

    await delete_instances({"instances": ["bw-1"]})
    await delete_configs({"configs": [{"service": "svc", "type": "http", "name": "one"}]})
    await delete_cache_files({"files": [{"plugin": "p", "job_name": "j", "file_name": "f"}]})
    for method in (client.delete_instances, client.delete_configs, client.delete_cache_files):
        method.assert_awaited_once()
    for tool, payload in (
        (delete_instances, {"instances": []}),
        (delete_configs, {"configs": []}),
        (delete_cache_files, {"files": []}),
    ):
        with pytest.raises(ToolValidationError):
            await tool(payload)


def test_read_only_tool_set() -> None:
    names = {d["name"] for d in Tools(SimpleNamespace(), read_only=True).list_descriptors()}  # type: ignore[arg-type]
    expected = {n for n in EXPECTED_TOOLS if n.startswith(("list_", "get_", "ping_"))}
    assert names == expected | {"diagnose_bunkerweb"}
