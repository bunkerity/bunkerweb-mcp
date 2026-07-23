"""Async client for the BunkerWeb control-plane API."""

from __future__ import annotations

import base64
from collections.abc import Iterable
from http import HTTPStatus
from typing import Any, TypeVar

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from .config import Settings, get_settings
from .exceptions import BunkerWebError
from .schemas.bans import BanRequestModel, BansResponse, UnbanRequestModel
from .schemas.cache import CacheFilesDeleteRequest, CacheResponse
from .schemas.common import ApiResponse, JsonDict
from .schemas.configs import (
    ConfigCreateRequest,
    ConfigKey,
    ConfigResponse,
    ConfigsDeleteRequest,
    ConfigsResponse,
    ConfigUpdateRequest,
)
from .schemas.core import AuthResponse, HealthResponse, PingResponse
from .schemas.global_config import GlobalConfigResponse, GlobalConfigUpdate
from .schemas.instances import (
    InstanceCreateRequest,
    InstancesDeleteRequest,
    InstancesResponse,
    InstanceUpdateRequest,
)
from .schemas.jobs import JobsResponse, RunJobsRequest
from .schemas.plugins import PluginsResponse
from .schemas.services import (
    ServiceCreateRequest,
    ServiceResponse,
    ServicesResponse,
    ServiceUpdateRequest,
)

T = TypeVar("T", bound=ApiResponse)
R = TypeVar("R")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        response = getattr(exc, "response", None)
        if response is None:
            return False
        return bool(response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR)
    return isinstance(exc, httpx.RequestError)


class BunkerWebClient:
    """Typed async wrapper around the BunkerWeb API."""

    def __init__(
        self, settings: Settings | None = None, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings or get_settings()
        headers = {
            "Accept": "application/json",
            "User-Agent": "mcp-bunkerweb/0.1.0",
        }
        # Use secure methods to get secret values
        api_token = self._settings.get_api_token()
        basic_password = self._settings.get_basic_password()

        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        elif self._settings.bunkerweb_basic_username and basic_password:
            basic_token = base64.b64encode(
                f"{self._settings.bunkerweb_basic_username}:{basic_password}".encode()
            ).decode("ascii")
            headers["Authorization"] = f"Basic {basic_token}"

        self._client = client or httpx.AsyncClient(
            base_url=str(self._settings.bunkerweb_base_url).rstrip("/"),
            headers=headers,
            timeout=self._settings.request_timeout_seconds,
            http2=True,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        allowed_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        retrying = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self._settings.max_retries),
            wait=wait_exponential(
                multiplier=self._settings.retry_backoff_initial or 0.5,
                max=self._settings.retry_backoff_max or 5.0,
            ),
            retry=retry_if_exception(_is_retryable),
        )

        async for attempt in retrying:  # pragma: no cover - tenacity handles iteration
            with attempt:
                response = await self._client.request(method, url, **kwargs)
                if allowed_statuses and response.status_code in allowed_statuses:
                    return response
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
                        raise
                    raise BunkerWebError(
                        message=self._extract_error_message(response),
                        status=HTTPStatus(response.status_code),
                    ) from exc
                return response

        raise RuntimeError("Retry loop exhausted")

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        response_model: type[R],
        allowed_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> R:
        response = await self._request(method, url, allowed_statuses=allowed_statuses, **kwargs)
        payload: JsonDict = response.json()
        return response_model.model_validate(payload)  # type: ignore[no-any-return, attr-defined]

    async def authenticate(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuthResponse:
        headers: dict[str, str] = {}
        body: dict[str, Any] = payload.copy() if payload else {}
        if username is not None:
            body.setdefault("username", username)
        if password is not None:
            body.setdefault("password", password)
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        kwargs: dict[str, Any] = {}
        if body:
            kwargs["json"] = body
        if headers:
            kwargs["headers"] = {**self._client.headers, **headers}
        response = await self._request("POST", "/auth", **kwargs)
        return AuthResponse.model_validate(response.json())

    async def ping(self) -> PingResponse:
        return await self._request_json("GET", "/ping", response_model=PingResponse)

    async def health(self) -> HealthResponse:
        response = await self._request("GET", "/health")
        return HealthResponse.model_validate(response.json())

    async def list_instances(self) -> InstancesResponse:
        return await self._request_json("GET", "/instances", response_model=InstancesResponse)

    async def ping_instances(self) -> ApiResponse:
        return await self._request_json("GET", "/instances/ping", response_model=ApiResponse)

    async def stop_instances(self) -> ApiResponse:
        return await self._request_json("POST", "/instances/stop", response_model=ApiResponse)

    async def get_instance(self, hostname: str) -> InstancesResponse:
        return await self._request_json(
            "GET", f"/instances/{hostname}", response_model=InstancesResponse
        )

    async def ping_instance(self, hostname: str) -> ApiResponse:
        return await self._request_json(
            "GET", f"/instances/{hostname}/ping", response_model=ApiResponse
        )

    async def stop_instance(self, hostname: str) -> ApiResponse:
        return await self._request_json(
            "POST", f"/instances/{hostname}/stop", response_model=ApiResponse
        )

    async def create_instance(self, payload: InstanceCreateRequest) -> InstancesResponse:
        return await self._request_json(
            "POST",
            "/instances",
            json=payload.model_dump(exclude_none=True),
            response_model=InstancesResponse,
        )

    async def update_instance(
        self, hostname: str, payload: InstanceUpdateRequest
    ) -> InstancesResponse:
        return await self._request_json(
            "PATCH",
            f"/instances/{hostname}",
            json=payload.model_dump(exclude_none=True),
            response_model=InstancesResponse,
        )

    async def delete_instances(self, payload: InstancesDeleteRequest) -> InstancesResponse:
        return await self._request_json(
            "DELETE",
            "/instances",
            json=payload.model_dump(exclude_none=True),
            response_model=InstancesResponse,
        )

    async def delete_instance(self, hostname: str) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            f"/instances/{hostname}",
            response_model=ApiResponse,
        )

    async def reload_instances(self, *, test: bool = True) -> ApiResponse:
        return await self._request_json(
            "POST",
            "/instances/reload",
            params={"test": str(test).lower()},
            response_model=ApiResponse,
        )

    async def reload_instance(self, hostname: str, *, test: bool = True) -> ApiResponse:
        return await self._request_json(
            "POST",
            f"/instances/{hostname}/reload",
            params={"test": str(test).lower()},
            response_model=ApiResponse,
        )

    async def list_bans(self) -> BansResponse:
        response = await self._request(
            "GET",
            "/bans",
            allowed_statuses={HTTPStatus.BAD_GATEWAY},
        )
        payload = response.json()
        if isinstance(payload, dict) and {"status", "message", "data"} & set(payload.keys()):
            return BansResponse.model_validate(payload)

        overall_status = "success"
        messages: list[str] = []
        node_statuses: list[str] = []
        if isinstance(payload, dict):
            for details in payload.values():
                if isinstance(details, dict):
                    status_value = details.get("status")
                    if isinstance(status_value, str):
                        node_statuses.append(status_value.lower())
                    msg = details.get("msg") or details.get("message")
                    if msg:
                        messages.append(str(msg))
        if node_statuses:
            if all(status == "success" for status in node_statuses):
                overall_status = "success"
            elif any(status == "success" for status in node_statuses):
                overall_status = "partial"
            else:
                overall_status = "error"
        message = "; ".join(filter(None, messages)) or None
        return BansResponse(status=overall_status, message=message, data=payload)

    async def ban(self, bans: Iterable[BanRequestModel]) -> BansResponse:
        payload = [item.model_dump(exclude_none=True, mode="json") for item in bans]
        body: Any
        if not payload:
            raise BunkerWebError("Ban payload must not be empty")
        body = payload if len(payload) > 1 else payload[0]
        return await self._request_json(
            "POST",
            "/bans",
            json=body,
            response_model=BansResponse,
            allowed_statuses={HTTPStatus.BAD_GATEWAY},
        )

    async def unban(self, bans: Iterable[UnbanRequestModel]) -> BansResponse:
        payload = [item.model_dump(exclude_none=True, mode="json") for item in bans]
        if not payload:
            raise BunkerWebError("Unban payload must not be empty")
        body = payload if len(payload) > 1 else payload[0]
        return await self._request_json(
            "DELETE",
            "/bans",
            json=body,
            response_model=BansResponse,
            allowed_statuses={HTTPStatus.BAD_GATEWAY},
        )

    async def list_services(self, *, with_drafts: bool = True) -> ServicesResponse:
        return await self._request_json(
            "GET",
            "/services",
            params={"with_drafts": str(with_drafts).lower()},
            response_model=ServicesResponse,
        )

    async def get_service(
        self,
        service: str,
        *,
        full: bool = False,
        methods: bool = True,
        with_drafts: bool = True,
    ) -> ServiceResponse:
        return await self._request_json(
            "GET",
            f"/services/{service}",
            params={
                "full": str(full).lower(),
                "methods": str(methods).lower(),
                "with_drafts": str(with_drafts).lower(),
            },
            response_model=ServiceResponse,
        )

    async def create_service(self, payload: ServiceCreateRequest) -> ServiceResponse:
        return await self._request_json(
            "POST",
            "/services",
            json=payload.model_dump(exclude_none=True),
            response_model=ServiceResponse,
        )

    async def update_service(self, service: str, payload: ServiceUpdateRequest) -> ServiceResponse:
        return await self._request_json(
            "PATCH",
            f"/services/{service}",
            json=payload.model_dump(exclude_none=True),
            response_model=ServiceResponse,
        )

    async def delete_service(self, service: str) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            f"/services/{service}",
            response_model=ApiResponse,
        )

    async def convert_service(self, service: str, *, convert_to: str) -> ApiResponse:
        return await self._request_json(
            "POST",
            f"/services/{service}/convert",
            params={"convert_to": convert_to},
            response_model=ApiResponse,
        )

    async def read_global_config(
        self, *, full: bool = False, methods: bool = False
    ) -> GlobalConfigResponse:
        params = {
            "full": str(full).lower(),
            "methods": str(methods).lower(),
        }
        return await self._request_json(
            "GET",
            "/global_settings",
            params=params,
            response_model=GlobalConfigResponse,
        )

    async def update_global_config(self, payload: dict[str, Any]) -> GlobalConfigResponse:
        validated = GlobalConfigUpdate.model_validate(payload)
        return await self._request_json(
            "PATCH",
            "/global_settings",
            json=validated.model_dump(),
            response_model=GlobalConfigResponse,
        )

    async def list_configs(
        self,
        *,
        service: str | None = None,
        config_type: str | None = None,
        with_drafts: bool = True,
        with_data: bool = False,
    ) -> ConfigsResponse:
        params: dict[str, Any] = {
            "with_drafts": str(with_drafts).lower(),
            "with_data": str(with_data).lower(),
        }
        if service is not None:
            params["service"] = service
        if config_type is not None:
            params["type"] = config_type
        return await self._request_json(
            "GET",
            "/configs",
            params=params,
            response_model=ConfigsResponse,
        )

    async def create_config(self, payload: ConfigCreateRequest) -> ConfigResponse:
        return await self._request_json(
            "POST",
            "/configs",
            json=payload.model_dump(exclude_none=True),
            response_model=ConfigResponse,
        )

    async def delete_configs(self, payload: ConfigsDeleteRequest) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            "/configs",
            json=payload.model_dump(exclude_none=True, by_alias=True),
            response_model=ApiResponse,
        )

    async def get_config(
        self,
        key: ConfigKey,
        *,
        with_data: bool = True,
    ) -> ConfigResponse:
        params = {"with_data": str(with_data).lower()}
        return await self._request_json(
            "GET",
            f"/configs/{key.service or 'global'}/{key.type}/{key.name}",
            params=params,
            response_model=ConfigResponse,
        )

    async def update_config(self, key: ConfigKey, payload: ConfigUpdateRequest) -> ConfigResponse:
        return await self._request_json(
            "PATCH",
            f"/configs/{key.service or 'global'}/{key.type}/{key.name}",
            json=payload.model_dump(exclude_none=True),
            response_model=ConfigResponse,
        )

    async def delete_config(self, key: ConfigKey) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            f"/configs/{key.service or 'global'}/{key.type}/{key.name}",
            response_model=ApiResponse,
        )

    async def upload_configs(
        self,
        *,
        files: list[tuple[str, bytes]],
        config_type: str,
        service: str | None = None,
        is_draft: bool = False,
    ) -> ConfigsResponse:
        form_files = [("files", (filename, content)) for filename, content in files]
        data = {"type": config_type, "is_draft": str(is_draft).lower()}
        if service is not None:
            data["service"] = service
        response = await self._request(
            "POST",
            "/configs/upload",
            files=form_files,
            data=data,
        )
        return ConfigsResponse.model_validate(response.json())

    async def update_config_upload(
        self,
        key: ConfigKey,
        *,
        file_name: str,
        content: bytes,
        new_service: str | None = None,
        new_type: str | None = None,
        new_name: str | None = None,
        new_is_draft: bool | None = None,
    ) -> ConfigResponse:
        data: dict[str, Any] = {}
        if new_service is not None:
            data["new_service"] = new_service
        if new_type is not None:
            data["new_type"] = new_type
        if new_name is not None:
            data["new_name"] = new_name
        if new_is_draft is not None:
            data["new_is_draft"] = str(new_is_draft).lower()
        response = await self._request(
            "PATCH",
            f"/configs/{key.service or 'global'}/{key.type}/{key.name}/upload",
            files={"file": (file_name, content)},
            data=data,
        )
        return ConfigResponse.model_validate(response.json())

    async def list_plugins(
        self, *, plugin_type: str = "all", with_data: bool = False
    ) -> PluginsResponse:
        params = {"type": plugin_type, "with_data": str(with_data).lower()}
        return await self._request_json(
            "GET",
            "/plugins",
            params=params,
            response_model=PluginsResponse,
        )

    async def upload_plugins(
        self,
        *,
        files: list[tuple[str, bytes]],
        method: str = "ui",
    ) -> PluginsResponse:
        form_files = [("files", (filename, content)) for filename, content in files]
        data = {"method": method}
        response = await self._request(
            "POST",
            "/plugins/upload",
            files=form_files,
            data=data,
        )
        return PluginsResponse.model_validate(response.json())

    async def delete_plugin(self, plugin_id: str) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            f"/plugins/{plugin_id}",
            response_model=ApiResponse,
        )

    async def list_cache(
        self,
        *,
        service: str | None = None,
        plugin: str | None = None,
        job_name: str | None = None,
        with_data: bool = False,
    ) -> CacheResponse:
        params: dict[str, Any] = {"with_data": str(with_data).lower()}
        if service is not None:
            params["service"] = service
        if plugin is not None:
            params["plugin"] = plugin
        if job_name is not None:
            params["job_name"] = job_name
        return await self._request_json(
            "GET",
            "/cache",
            params=params,
            response_model=CacheResponse,
        )

    async def delete_cache_files(self, payload: CacheFilesDeleteRequest) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            "/cache",
            json=payload.model_dump(exclude_none=True, by_alias=True),
            response_model=ApiResponse,
        )

    async def fetch_cache_file(
        self,
        *,
        service: str,
        plugin_id: str,
        job_name: str,
        file_name: str,
        download: bool = False,
    ) -> dict[str, Any]:
        params = {"download": str(download).lower()}
        response = await self._request(
            "GET",
            f"/cache/{service}/{plugin_id}/{job_name}/{file_name}",
            params=params,
        )
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            return response.json()  # type: ignore[no-any-return]
        return {
            "filename": file_name,
            "content_type": content_type,
            "data_base64": base64.b64encode(response.content).decode("ascii"),
        }

    async def delete_cache_file(
        self,
        *,
        service: str,
        plugin_id: str,
        job_name: str,
        file_name: str,
    ) -> ApiResponse:
        return await self._request_json(
            "DELETE",
            f"/cache/{service}/{plugin_id}/{job_name}/{file_name}",
            response_model=ApiResponse,
        )

    async def list_jobs(self) -> JobsResponse:
        return await self._request_json("GET", "/jobs", response_model=JobsResponse)

    async def run_jobs(self, payload: RunJobsRequest) -> ApiResponse:
        return await self._request_json(
            "POST",
            "/jobs/run",
            json=payload.model_dump(exclude_none=True),
            response_model=ApiResponse,
        )

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text
        if isinstance(payload, dict):
            return str(payload.get("message") or payload)
        return str(payload)

    async def __aenter__(self) -> BunkerWebClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
