"""Read-only diagnostics report independent upstream checks without exposing values."""

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bunkerweb_mcp.exceptions import BunkerWebError
from bunkerweb_mcp.schemas.global_config import GlobalConfigResponse
from bunkerweb_mcp.schemas.instances import InstancesResponse
from bunkerweb_mcp.schemas.services import ServiceResponse
from bunkerweb_mcp.tools.diagnose_handlers import handle_diagnose
from bunkerweb_mcp.tools.params import DiagnoseParams
from bunkerweb_mcp.tools.registry import Tools
from bunkerweb_mcp.upstream import reset_upstream_state

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_upstream() -> Iterator[None]:
    reset_upstream_state()
    yield
    reset_upstream_state()


def _client() -> Any:
    return SimpleNamespace(
        base_url="http://bw:8888",
        ping=AsyncMock(),
        get_openapi_version=AsyncMock(return_value="1.6.17"),
        list_instances=AsyncMock(
            return_value=InstancesResponse(data=[{"status": "up"}, {"status": "up"}])
        ),
        read_global_config=AsyncMock(
            return_value=GlobalConfigResponse(data={"MULTISITE": "yes", "TOKEN": "hidden"})
        ),
        get_service=AsyncMock(return_value=ServiceResponse(data={})),
    )


async def test_diagnose_all_ok() -> None:
    client = _client()
    result = await handle_diagnose(client, DiagnoseParams())
    assert next(iter(result)) == "summary"
    assert result == {
        "summary": "API OK · AUTH OK · MULTISITE=yes · 2 instances (2 up)",
        "api": {"host": "bw:8888", "reachable": True},
        "auth": True,
        "version": "1.6.17",
        "multisite": "yes",
        "instances": {"total": 2, "up": 2},
        "service": None,
        "live": "Live state cannot be checked on BunkerWeb 1.6.",
    }
    client.ping.assert_awaited_once_with()
    client.list_instances.assert_awaited_once_with()
    client.read_global_config.assert_awaited_once_with(full=True, methods=False)
    client.get_service.assert_not_awaited()


async def test_diagnose_auth_failure_reported() -> None:
    client = _client()
    client.list_instances.side_effect = BunkerWebError("secret auth detail", status=401)
    result = await handle_diagnose(client, DiagnoseParams())
    assert "AUTH FAIL" in result["summary"]
    assert result["auth"] is False
    assert result["instances"] is None
    assert result["api"]["reachable"] is True
    assert "secret" not in json.dumps(result)


async def test_diagnose_version_unknown() -> None:
    client = _client()
    client.get_openapi_version.side_effect = RuntimeError("secret")
    result = await handle_diagnose(client, DiagnoseParams())
    assert result["version"] == "unknown (strictest rules applied)"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.7.0~alpha", "1.7.0~alpha"),
        ("1.6.15-rc1", "1.6.15-rc1"),
        ("dev", "unknown (strictest rules applied)"),
    ],
)
async def test_diagnose_raw_validated_version(raw: str, expected: str) -> None:
    client = _client()
    client.get_openapi_version.return_value = raw
    result = await handle_diagnose(client, DiagnoseParams())
    assert result["version"] == expected
    client.get_openapi_version.assert_awaited_once_with()


async def test_diagnose_service_owners() -> None:
    client = _client()
    client.get_service.return_value = ServiceResponse(
        data={
            "IS_DRAFT": {"value": "yes", "global": False, "method": "default"},
            "A": {"value": "secret", "global": False, "method": "api"},
            "B": {"value": "secret", "global": False, "method": "scheduler"},
            "C": {"value": None, "global": False, "method": "scheduler"},
            "D": {"value": "secret", "global": True, "method": "ui"},
            "E": {"value": "secret", "method": "ui"},
            "F": {"value": "secret", "global": False, "method": "default"},
        }
    )
    result = await handle_diagnose(client, DiagnoseParams(service="example.com"))
    assert result["service"] == {
        "exists": True,
        "draft": True,
        "owners": {"api": 1, "scheduler": 2},
    }
    assert "secret" not in json.dumps(result)
    client.get_service.assert_awaited_once_with(
        "example.com", full=True, methods=True, with_drafts=True
    )


async def test_diagnose_host_strips_credentials() -> None:
    client = _client()
    client.base_url = "http://user:pw@bw:8888/path?token=secret#fragment"
    result = await handle_diagnose(client, DiagnoseParams())
    assert result["api"]["host"] == "bw:8888"
    assert all(value not in json.dumps(result) for value in ("user", "pw", "secret"))


async def test_diagnose_independent_failures() -> None:
    client = _client()
    client.ping.side_effect = RuntimeError("secret")
    client.read_global_config.side_effect = RuntimeError("secret")
    client.get_service.side_effect = BunkerWebError("secret", status=404)
    client.list_instances.return_value = InstancesResponse(
        data=[{"status": "up"}, {"status": "down"}]
    )
    result = await handle_diagnose(client, DiagnoseParams(service="example.com"))
    assert "API FAIL" in result["summary"]
    assert "AUTH OK" in result["summary"]
    assert "MULTISITE=?" in result["summary"]
    assert "SERVICE FAIL" in result["summary"]
    assert result["api"]["reachable"] is False
    assert result["multisite"] is None
    assert result["instances"] == {"total": 2, "up": 1}
    assert result["service"] == {"exists": False, "draft": None, "owners": None}
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize(
    ("error", "exists"),
    [
        (BunkerWebError("secret", status=404), False),
        (BunkerWebError("secret", status=503), None),
        (BunkerWebError("secret", status=401), None),
        (BunkerWebError("secret", status=403), None),
        (TimeoutError("secret"), None),
        (ValueError("secret"), None),
    ],
)
async def test_diagnose_service_existence_on_read_failure(
    error: Exception, exists: bool | None
) -> None:
    client = _client()
    client.get_service.side_effect = error
    result = await handle_diagnose(client, DiagnoseParams(service="example.com"))
    assert result["service"] == {"exists": exists, "draft": None, "owners": None}
    assert "secret" not in json.dumps(result)


async def test_diagnose_nullable_draft() -> None:
    client = _client()
    client.get_service.return_value = ServiceResponse(data={"IS_DRAFT": {"value": None}})
    result = await handle_diagnose(client, DiagnoseParams(service="example.com"))
    assert result["service"] == {"exists": True, "draft": None, "owners": {}}


async def test_diagnose_successful_auth_with_missing_instance_data() -> None:
    client = _client()
    client.list_instances.return_value = InstancesResponse(data=None)
    result = await handle_diagnose(client, DiagnoseParams())
    assert result["auth"] is True
    assert result["instances"] is None
    assert "instances FAIL" in result["summary"]


@pytest.mark.parametrize("data", [None, {}, {"MULTISITE": "secret"}])
async def test_diagnose_unknown_multisite(data: dict[str, str] | None) -> None:
    client = _client()
    client.read_global_config.return_value = GlobalConfigResponse(data=data)
    result = await handle_diagnose(client, DiagnoseParams())
    assert result["multisite"] is None
    assert "MULTISITE=?" in result["summary"]
    assert "secret" not in json.dumps(result)


async def test_diagnose_registered_in_read_only_mode() -> None:
    tools = Tools(_client(), read_only=True)
    descriptor = next(item for item in tools.list_descriptors() if item["name"] == "diagnose")
    assert descriptor["read_only"] is True
    assert descriptor["destructive"] is False
    assert descriptor["description"] == (
        "Read-only check of the connected BunkerWeb: reachability, authentication, version, "
        "MULTISITE, instances, and optionally who owns a service's settings."
    )
    handler = tools.get_tool("diagnose")
    assert handler is not None
    result = await handler(DiagnoseParams())
    assert result["auth"] is True
