import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.main import LOGGER, create_app
from bunkerweb_mcp.schemas.bans import BansResponse
from bunkerweb_mcp.schemas.common import ApiResponse
from bunkerweb_mcp.schemas.configs import ConfigResponse, ConfigsResponse
from bunkerweb_mcp.schemas.core import HealthResponse, PingResponse
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.instances import InstancesResponse
from bunkerweb_mcp.schemas.jobs import JobsResponse
from bunkerweb_mcp.schemas.services import ServiceResponse, ServicesResponse

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

SERVICE_LIST_PAYLOAD = [
    {
        "id": "demo.mcp-test.local",
        "method": "api",
        "is_draft": False,
        "creation_date": "2025-12-11T22:26:57+00:00",
        "last_update": "2025-12-11T22:26:57+00:00",
        "template": "",
    },
    {
        "id": "integration.api.test",
        "method": "api",
        "is_draft": False,
        "creation_date": "2025-12-12T08:13:51+00:00",
        "last_update": "2025-12-12T08:13:51+00:00",
        "template": "",
    },
    {
        "id": "www.example.com",
        "method": "ui",
        "is_draft": False,
        "creation_date": "2025-12-11T21:04:58+00:00",
        "last_update": "2025-12-11T21:04:58+00:00",
        "template": "low",
    },
]


GLOBAL_CONFIG_PAYLOAD = {
    "USE_REDIS": {
        "value": "yes",
        "global": True,
        "method": "scheduler",
        "default": "no",
        "template": None,
    },
    "REDIS_HOST": {
        "value": "redis-bunkerweb.bunkerweb.svc.cluster.local",
        "global": True,
        "method": "scheduler",
        "default": "",
        "template": None,
    },
    "DNS_RESOLVERS": {
        "value": "kube-dns.kube-system.svc.cluster.local",
        "global": True,
        "method": "scheduler",
        "default": "127.0.0.11",
        "template": None,
    },
    "KEEP_UPSTREAM_HEADERS": {
        "value": "Content-Security-Policy Permissions-Policy X-Frame-Options",
        "global": True,
        "method": "default",
        "default": "Content-Security-Policy Permissions-Policy X-Frame-Options",
        "template": None,
    },
}

CONFIG_ITEM_PAYLOAD = {
    "type": "http",
    "name": "integration-snippet",
    "checksum": "69271e5a7ea91b567ee8f1bae82ce7bf38dd784fc5e9435c793a303dbfca57f2",
    "method": "api",
    "template": None,
    "data": "# sample",
    "service": "global",
}

CONFIG_LIST_PAYLOAD = [CONFIG_ITEM_PAYLOAD]

PROMPTS_PATH = Path(__file__).resolve().parents[1] / "prompts" / "tool_prompts.json"
TOOL_PROMPTS = json.loads(PROMPTS_PATH.read_text(encoding="utf-8")).get("tools", {})


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
            },
            {
                "ip": "198.51.100.250",
                "reason": "api",
                "exp": 84438,
                "permanent": False,
                "service": "unknown",
                "ban_scope": "global",
                "country": "unknown",
                "date": 1765532424,
            },
        ],
    }
}

JOBS_LIST_PAYLOAD = {
    "anonymous-report": {
        "plugin_id": "misc",
        "every": "day",
        "reload": False,
        "async": True,
        "history": [
            {
                "start_date": "2025-12-12T08:45:06+00:00",
                "end_date": "2025-12-12T08:45:08+00:00",
                "success": True,
            }
        ],
        "cache": [
            {
                "service_id": None,
                "file_name": "last_report.json",
                "last_update": "2025/12/11, 19:04:08 ",
                "checksum": "7aa0cc6d1fc0d24bd855f300b8ab9890be6589323b44807d971d0f318040d189",
            }
        ],
    },
    "backup-data": {
        "plugin_id": "backup",
        "every": "day",
        "reload": False,
        "async": True,
        "history": [
            {
                "start_date": "2025-12-12T08:45:08+00:00",
                "end_date": "2025-12-12T08:45:09+00:00",
                "success": True,
            }
        ],
        "cache": [
            {
                "service_id": None,
                "file_name": "backup.json",
                "last_update": "2025/12/11, 19:32:56 ",
                "checksum": "b6bd0309a1602dbb3d75c435c125cafd6328ede8d6828bf050e0cf725f2473b6",
            }
        ],
    },
}


class DummyClient:
    async def close(self) -> None:
        return None

    async def ping(self) -> PingResponse:
        return PingResponse(status="ok", message="pong")

    async def health(self) -> HealthResponse:
        return HealthResponse(status="ok", details={})

    async def list_instances(self) -> InstancesResponse:
        return InstancesResponse(status="success", data=[])

    async def reload_instances(self, *, test: bool) -> ApiResponse:
        return ApiResponse(status="success", message=f"reload_all:{test}")

    async def reload_instance(self, hostname: str, *, test: bool) -> ApiResponse:
        return ApiResponse(status="success", message=f"reload:{hostname}:{test}")

    async def list_bans(self) -> BansResponse:
        return BansResponse(status="success", message="success", data=BANS_LIST_PAYLOAD)

    async def ban(self, bans):  # type: ignore[no-untyped-def]
        return BansResponse(status="success")

    async def unban(self, bans):  # type: ignore[no-untyped-def]
        return BansResponse(status="success")

    async def list_services(self, *, with_drafts: bool) -> ServicesResponse:
        return ServicesResponse(status="success", data=SERVICE_LIST_PAYLOAD)

    async def get_service(
        self, service: str, *, full: bool, methods: bool, with_drafts: bool
    ) -> ServiceResponse:
        return ServiceResponse(status="success", service=service, data=SERVICE_CONFIG_PAYLOAD)

    async def create_service(self, payload):  # type: ignore[no-untyped-def]
        return ServiceResponse(
            status="success", service=payload.server_name, data=SERVICE_CONFIG_PAYLOAD
        )

    async def update_service(self, service: str, payload):  # type: ignore[no-untyped-def]
        return ServiceResponse(status="success", service=service, data=SERVICE_CONFIG_PAYLOAD)

    async def delete_service(self, service: str) -> ApiResponse:
        return ApiResponse(status="success", message=f"deleted:{service}")

    async def convert_service(self, service: str, *, convert_to: str) -> ApiResponse:
        return ApiResponse(status="success", message=f"convert:{service}:{convert_to}")

    async def read_global_config(self, *, full: bool, methods: bool) -> GlobalConfigResponse:
        return GlobalConfigResponse(status="success", data=GLOBAL_CONFIG_PAYLOAD)

    async def update_global_config(self, config):  # type: ignore[no-untyped-def]
        return GlobalConfigResponse(status="success")

    async def list_configs(self, *, service, config_type, with_drafts, with_data):  # type: ignore[no-untyped-def]
        return ConfigsResponse(status="success", data=CONFIG_LIST_PAYLOAD)

    async def get_config(self, key, *, with_data: bool) -> ConfigResponse:  # type: ignore[no-untyped-def]
        return ConfigResponse(status="success", data=CONFIG_ITEM_PAYLOAD)

    async def create_config(self, payload):  # type: ignore[no-untyped-def]
        return ConfigResponse(status="success")

    async def update_config(self, key, payload):  # type: ignore[no-untyped-def]
        return ConfigResponse(status="success")

    async def delete_config(self, key) -> ApiResponse:  # type: ignore[no-untyped-def]
        return ApiResponse(status="success")

    async def delete_configs(self, payload):  # type: ignore[no-untyped-def]
        return ApiResponse(status="success")

    async def list_jobs(self) -> JobsResponse:
        return JobsResponse(status="success", data=JOBS_LIST_PAYLOAD)

    async def run_jobs(self, payload):  # type: ignore[no-untyped-def]
        return ApiResponse(status="success", message=f"run:{len(payload.jobs)}")


@pytest.fixture()
def app():  # noqa: D401
    dummy_settings = Settings.model_validate(
        {
            "BUNKERWEB_BASE_URL": "http://localhost:8888",
            "BUNKERWEB_API_TOKEN": "token",
            "BUNKERWEB_WEBSOCKET_TOKEN": "secret",
            "BUNKERWEB_LOG_LEVEL": "INFO",
        }
    )
    with (
        patch("bunkerweb_mcp.main.get_settings", return_value=dummy_settings),
        patch("bunkerweb_mcp.main.BunkerWebClient", return_value=DummyClient()),
    ):
        yield create_app()


@pytest.mark.asyncio
async def test_tools_endpoint_returns_descriptors(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/tools", headers={"X-MCP-Token": "secret"})
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    names = {item["name"] for item in payload}
    expected_names = {
        "ping",
        "health",
        "list_instances",
        "reload_instances",
        "reload_instance",
        "list_bans",
        "ban_ip",
        "unban_ip",
        "list_services",
        "get_service",
        "delete_service",
    }
    assert expected_names.issubset(names)
    assert all("input_schema" in item for item in payload)
    for item in payload:
        if item["name"] in TOOL_PROMPTS:
            assert item.get("prompt") == TOOL_PROMPTS[item["name"]]


@pytest.mark.asyncio
async def test_rpc_requires_token(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/rpc", json={"id": "1", "tool": "ping", "params": {}})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MCP token"


@pytest.mark.asyncio
async def test_rpc_logs_metrics(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch.object(LOGGER, "info") as info_mock:
            response = await client.post(
                "/rpc",
                headers={"X-MCP-Token": "secret"},
                json={"id": "1", "tool": "ping", "params": {}},
            )
    assert response.status_code == 200
    info_mock.assert_called()
    args, kwargs = info_mock.call_args
    assert args[0] == "tool_call"
    metrics = kwargs.get("extra", {}).get("metrics", {})
    assert metrics.get("tool") == "ping"
    assert "duration_seconds" in metrics


@pytest.mark.asyncio
async def test_rpc_ping_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "ping", "tool": "ping", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "ping"
    assert payload["result"] == {"status": "ok", "message": "pong"}
    assert payload["prompt"] == TOOL_PROMPTS["ping"]


@pytest.mark.asyncio
async def test_rpc_health_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "health", "tool": "health", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "health"
    assert payload["result"] == {"status": "ok", "details": {}}


@pytest.mark.asyncio
async def test_rpc_list_services_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "list", "tool": "list_services", "params": {"with_drafts": True}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "list"
    assert payload["result"]["status"] == "success"
    assert payload["result"]["data"] == SERVICE_LIST_PAYLOAD
    assert payload["prompt"] == TOOL_PROMPTS["list_services"]


@pytest.mark.asyncio
async def test_rpc_list_bans_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "bans-list", "tool": "list_bans", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "bans-list"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["message"] == "success"
    assert result["data"] == BANS_LIST_PAYLOAD
    assert payload["prompt"] == TOOL_PROMPTS["list_bans"]


@pytest.mark.asyncio
async def test_rpc_ban_ip_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "ban-ip",
                "tool": "ban_ip",
                "params": {"bans": [{"ip": "198.51.100.1", "exp": 60, "reason": "tests"}]},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "ban-ip"
    result = payload["result"]
    assert result == {"status": "success"}
    assert payload["prompt"] == TOOL_PROMPTS["ban_ip"]


@pytest.mark.asyncio
async def test_rpc_unban_ip_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "unban-ip",
                "tool": "unban_ip",
                "params": {"bans": [{"ip": "198.51.100.1"}]},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "unban-ip"
    result = payload["result"]
    assert result == {"status": "success"}
    assert payload["prompt"] == TOOL_PROMPTS["unban_ip"]


@pytest.mark.asyncio
async def test_rpc_list_instances_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "instances", "tool": "list_instances", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "instances"
    assert payload["result"] == {"status": "success", "data": []}


@pytest.mark.asyncio
async def test_rpc_reload_instances_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "reload-all", "tool": "reload_instances", "params": {"test": True}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "reload-all"
    assert payload["result"] == {"status": "success", "message": "reload_all:True"}
    assert payload["prompt"] == TOOL_PROMPTS["reload_instances"]


@pytest.mark.asyncio
async def test_rpc_reload_instance_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "reload-one",
                "tool": "reload_instance",
                "params": {"hostname": "edge-1", "test": False},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "reload-one"
    assert payload["result"] == {"status": "success", "message": "reload:edge-1:False"}


@pytest.mark.asyncio
async def test_rpc_get_service_returns_config(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "get",
                "tool": "get_service",
                "params": {
                    "service": "integration.api.test",
                    "full": True,
                    "methods": True,
                    "with_drafts": True,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "get"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["service"] == "integration.api.test"
    assert result["data"] == SERVICE_CONFIG_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_create_service_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "create",
                "tool": "create_service",
                "params": {
                    "server_name": "integration.api.test",
                    "is_draft": False,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "create"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["service"] == "integration.api.test"
    assert result["data"] == SERVICE_CONFIG_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_update_service_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "update",
                "tool": "update_service",
                "params": {
                    "service": "integration.api.test",
                    "server_name": "integration.api.test",
                    "is_draft": False,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "update"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["service"] == "integration.api.test"
    assert result["data"] == SERVICE_CONFIG_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_delete_service_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "delete",
                "tool": "delete_service",
                "params": {
                    "service": "integration.api.test",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "delete"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["message"] == "deleted:integration.api.test"


@pytest.mark.asyncio
async def test_rpc_convert_service_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "convert",
                "tool": "convert_service",
                "params": {
                    "service": "integration.api.test",
                    "convert_to": "draft",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "convert"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["message"] == "convert:integration.api.test:draft"


@pytest.mark.asyncio
async def test_rpc_jobs_list_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={"id": "jobs-list", "tool": "jobs_list", "params": {}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "jobs-list"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["data"] == JOBS_LIST_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_jobs_run_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "jobs-run",
                "tool": "jobs_run",
                "params": {
                    "jobs": [
                        {"plugin": "misc", "name": "anonymous-report"},
                        {"plugin": "backup", "name": "backup-data"},
                    ]
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "jobs-run"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["message"] == "run:2"


@pytest.mark.asyncio
async def test_rpc_configs_list_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-list",
                "tool": "configs_list",
                "params": {
                    "with_data": True,
                    "with_drafts": True,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-list"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["data"] == CONFIG_LIST_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_config_get_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-get",
                "tool": "config_get",
                "params": {
                    "service": None,
                    "type": "http",
                    "name": "integration-snippet",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-get"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["data"] == CONFIG_ITEM_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_config_create_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-create",
                "tool": "config_create",
                "params": {
                    "service": None,
                    "type": "http",
                    "name": "integration-snippet",
                    "data": "# sample",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-create"
    result = payload["result"]
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_rpc_config_update_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-update",
                "tool": "config_update",
                "params": {
                    "service": None,
                    "type": "http",
                    "name": "integration-snippet",
                    "data": "# sample updated",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-update"
    result = payload["result"]
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_rpc_config_delete_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-delete",
                "tool": "config_delete",
                "params": {
                    "service": None,
                    "type": "http",
                    "name": "integration-snippet",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-delete"
    result = payload["result"]
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_rpc_configs_delete_bulk_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "cfg-delete-bulk",
                "tool": "configs_delete_bulk",
                "params": {
                    "configs": [
                        {
                            "service": None,
                            "type": "http",
                            "name": "integration-snippet",
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "cfg-delete-bulk"
    result = payload["result"]
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_rpc_global_config_read_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "gc-read",
                "tool": "global_config_read",
                "params": {
                    "full": True,
                    "methods": True,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "gc-read"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["data"] == GLOBAL_CONFIG_PAYLOAD


@pytest.mark.asyncio
async def test_rpc_global_config_update_returns_payload(app) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/rpc",
            headers={"X-MCP-Token": "secret"},
            json={
                "id": "gc-update",
                "tool": "global_config_update",
                "params": {
                    "config": {
                        "KEEP_UPSTREAM_HEADERS": "Content-Security-Policy Permissions-Policy X-Frame-Options",
                    },
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "gc-update"
    result = payload["result"]
    assert result == {"status": "success"}


def test_websocket_requires_token(app) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws") as ws,
    ):
        ws.receive_json()
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_ping_flow(app) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws?token=secret") as ws:
        ws.send_json({"id": "1", "tool": "ping", "params": {}})
        message = ws.receive_json()
    assert message["id"] == "1"
    assert message["result"]["status"] == "ok"
    assert message["result"]["message"] == "pong"


def test_websocket_missing_tool_error(app) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws?token=secret") as ws:
        ws.send_json({"id": "abc"})
        message = ws.receive_json()
    assert message["id"] == "abc"
    assert message["error"] == {
        "code": "missing_tool",
        "message": "Missing 'tool' field",
    }


def test_websocket_invalid_json(app) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws?token=secret") as ws:
        ws.send_text("not-json")
        message = ws.receive_json()
    assert message == {"error": {"code": "invalid_json", "message": "Invalid JSON"}}
