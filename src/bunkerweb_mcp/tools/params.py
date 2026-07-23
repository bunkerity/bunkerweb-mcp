"""Parameter models for MCP tools."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, IPvAnyAddress

if TYPE_CHECKING:
    from ..schemas.bans import BanRequestModel, BansResponse, UnbanRequestModel
    from ..schemas.cache import CacheFilesDeleteRequest
    from ..schemas.common import ApiResponse
    from ..schemas.configs import ConfigUpdateRequest
    from ..schemas.core import AuthResponse, HealthResponse, PingResponse
    from ..schemas.instances import (
        InstanceCreateRequest,
        InstancesDeleteRequest,
        InstancesResponse,
        InstanceUpdateRequest,
    )
    from ..schemas.jobs import RunJobsRequest
    from ..schemas.services import ServiceResponse, ServicesResponse


@runtime_checkable
class BunkerWebClientProtocol(Protocol):
    """Protocol defining the interface for BunkerWeb API client."""

    async def authenticate(
        self,
        *,
        username: str | None,
        password: str | None,
        payload: dict[str, Any] | None,
    ) -> AuthResponse: ...

    async def ping(self) -> PingResponse: ...

    async def health(self) -> HealthResponse: ...

    async def list_instances(self) -> InstancesResponse: ...

    async def ping_instances(self) -> ApiResponse: ...

    async def stop_instances(self) -> ApiResponse: ...

    async def reload_instances(self, *, test: bool) -> ApiResponse: ...

    async def reload_instance(self, hostname: str, *, test: bool) -> ApiResponse: ...

    async def get_instance(self, hostname: str) -> InstancesResponse: ...

    async def ping_instance(self, hostname: str) -> ApiResponse: ...

    async def stop_instance(self, hostname: str) -> ApiResponse: ...

    async def create_instance(self, payload: InstanceCreateRequest) -> InstancesResponse: ...

    async def update_instance(
        self, hostname: str, payload: InstanceUpdateRequest
    ) -> InstancesResponse: ...

    async def delete_instances(self, payload: InstancesDeleteRequest) -> InstancesResponse: ...

    async def delete_instance(self, hostname: str) -> ApiResponse: ...

    async def list_bans(self) -> BansResponse: ...

    async def ban(self, bans: Any) -> BansResponse: ...

    async def unban(self, bans: Any) -> BansResponse: ...

    async def list_services(self, *, with_drafts: bool) -> ServicesResponse: ...

    async def get_service(
        self,
        service: str,
        *,
        full: bool,
        methods: bool,
        with_drafts: bool,
    ) -> ServiceResponse: ...

    async def create_service(self, payload: Any) -> ServiceResponse: ...

    async def update_service(self, service: str, payload: Any) -> ServiceResponse: ...

    async def delete_service(self, service: str) -> ApiResponse: ...

    async def convert_service(self, service: str, *, convert_to: str) -> ApiResponse: ...

    async def read_global_config(self, *, full: bool, methods: bool) -> ApiResponse: ...

    async def update_global_config(self, payload: dict[str, Any]) -> ApiResponse: ...

    async def list_configs(
        self,
        *,
        service: str | None,
        config_type: str | None,
        with_drafts: bool,
        with_data: bool,
    ) -> ApiResponse: ...

    async def create_config(self, payload: Any) -> ApiResponse: ...

    async def delete_configs(self, payload: Any) -> ApiResponse: ...

    async def get_config(self, key: Any, *, with_data: bool) -> ApiResponse: ...

    async def update_config(self, key: Any, payload: ConfigUpdateRequest) -> ApiResponse: ...

    async def delete_config(self, key: Any) -> ApiResponse: ...

    async def upload_configs(
        self,
        *,
        files: list[tuple[str, bytes]],
        config_type: str,
        service: str | None,
        is_draft: bool,
    ) -> ApiResponse: ...

    async def update_config_upload(
        self,
        key: Any,
        *,
        file_name: str,
        content: bytes,
        new_service: str | None,
        new_type: str | None,
        new_name: str | None,
        new_is_draft: bool | None,
    ) -> ApiResponse: ...

    async def list_plugins(self, *, plugin_type: str, with_data: bool) -> ApiResponse: ...

    async def upload_plugins(
        self, *, files: list[tuple[str, bytes]], method: str
    ) -> ApiResponse: ...

    async def delete_plugin(self, plugin_id: str) -> ApiResponse: ...

    async def list_cache(
        self,
        *,
        service: str | None,
        plugin: str | None,
        job_name: str | None,
        with_data: bool,
    ) -> ApiResponse: ...

    async def delete_cache_files(self, payload: CacheFilesDeleteRequest) -> ApiResponse: ...

    async def fetch_cache_file(
        self,
        *,
        service: str,
        plugin_id: str,
        job_name: str,
        file_name: str,
        download: bool,
    ) -> dict[str, Any]: ...

    async def delete_cache_file(
        self,
        *,
        service: str,
        plugin_id: str,
        job_name: str,
        file_name: str,
    ) -> ApiResponse: ...

    async def list_jobs(self) -> ApiResponse: ...

    async def run_jobs(self, payload: RunJobsRequest) -> ApiResponse: ...


class _BaseToolParams(BaseModel):
    """Base class for tool parameter validation."""

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }


class EmptyParams(_BaseToolParams):
    """Placeholder for tools without parameters."""


class ReloadParams(_BaseToolParams):
    test: bool = Field(True, description="Run the reload in validation-only mode")


class HostnameParams(ReloadParams):
    hostname: str = Field(..., min_length=1, description="Target instance hostname")


class BanPayload(_BaseToolParams):
    ip: IPvAnyAddress = Field(..., description="IP address to ban")
    exp: int = Field(86400, ge=0, description="Expiration in seconds (0 means permanent)")
    reason: str = Field("api", min_length=1, max_length=255, description="Audit log reason")
    service: str | None = Field(None, description="Optional service identifier")

    def to_model(self) -> BanRequestModel:
        from ..schemas.bans import BanRequestModel

        return BanRequestModel.model_validate(self.model_dump())


class UnbanPayload(_BaseToolParams):
    ip: IPvAnyAddress = Field(..., description="IP address to unban")
    service: str | None = Field(None, description="Optional service identifier")

    def to_model(self) -> UnbanRequestModel:
        from ..schemas.bans import UnbanRequestModel

        return UnbanRequestModel.model_validate(self.model_dump())


class BanParams(_BaseToolParams):
    bans: list[BanPayload] = Field(..., min_length=1, description="List of ban requests")


class UnbanParams(_BaseToolParams):
    bans: list[UnbanPayload] = Field(..., min_length=1, description="List of unban requests")


class ListServicesParams(_BaseToolParams):
    with_drafts: bool = Field(True, description="Include draft services")


class GetServiceParams(_BaseToolParams):
    service: str = Field(..., min_length=1, description="Service identifier")
    full: bool = Field(False, description="Include derived defaults")
    methods: bool = Field(True, description="Include method metadata")
    with_drafts: bool = Field(True, description="Include draft services")


class DeleteServiceParams(_BaseToolParams):
    service: str = Field(..., min_length=1, description="Service identifier to delete")


class AuthParams(_BaseToolParams):
    username: str | None = Field(default=None, description="Username for Basic auth")
    password: str | None = Field(default=None, description="Password for Basic auth")
    payload: dict[str, Any] | None = Field(default=None, description="Optional JSON payload")


class SimpleHostnameParams(_BaseToolParams):
    hostname: str = Field(..., min_length=1, description="Instance hostname")


class InstanceCreateParams(_BaseToolParams):
    hostname: str = Field(..., description="Instance hostname")
    name: str | None = Field(default=None, description="Friendly instance name")
    port: int | None = Field(default=None, ge=1, le=65535)
    listen_https: bool | None = Field(default=None)
    https_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None)
    method: str | None = Field(default=None)


class InstanceUpdateParams(_BaseToolParams):
    hostname: str = Field(..., description="Instance hostname to update")
    name: str | None = Field(default=None)
    port: int | None = Field(default=None, ge=1, le=65535)
    listen_https: bool | None = Field(default=None)
    https_port: int | None = Field(default=None, ge=1, le=65535)
    server_name: str | None = Field(default=None)
    method: str | None = Field(default=None)


class InstancesDeleteParams(_BaseToolParams):
    instances: list[str] = Field(..., min_length=1, description="Hostnames to delete")


class ServiceCreateParams(_BaseToolParams):
    server_name: str = Field(..., description="Primary server name")
    is_draft: bool = Field(default=False, description="Create as draft")
    variables: dict[str, str] | None = Field(default=None, description="Service variables")


class ServiceUpdateParams(_BaseToolParams):
    service: str = Field(..., description="Existing service identifier")
    server_name: str | None = Field(default=None, description="Rename the service")
    is_draft: bool | None = Field(default=None, description="Toggle draft state")
    variables: dict[str, str] | None = Field(default=None, description="Variables to upsert")


class ServiceConvertParams(_BaseToolParams):
    service: str = Field(..., description="Service identifier")
    convert_to: str = Field(..., pattern="^(online|draft)$", description="Target state")


class GlobalConfigReadParams(_BaseToolParams):
    full: bool = Field(default=False, description="Include defaulted settings")
    methods: bool = Field(default=False, description="Include method metadata")


class GlobalConfigUpdateParams(_BaseToolParams):
    config: dict[str, Any] = Field(..., description="Key-value pairs to update")


class ConfigListParams(_BaseToolParams):
    service: str | None = Field(default=None, description="Service identifier or global")
    type: str | None = Field(default=None, description="Configuration type filter")
    with_drafts: bool = Field(default=True)
    with_data: bool = Field(default=False)


class ConfigKeyParams(_BaseToolParams):
    service: str | None = Field(default=None, description="Service identifier or global")
    type: str = Field(..., description="Configuration type")
    name: str = Field(..., description="Configuration name")


class ConfigCreateParams(ConfigKeyParams):
    data: str = Field(..., description="Configuration content")
    is_draft: bool = Field(default=False, description="Create as draft")


class ConfigUpdateParams(ConfigKeyParams):
    new_service: str | None = Field(default=None)
    new_type: str | None = Field(default=None)
    new_name: str | None = Field(default=None)
    data: str | None = Field(default=None)
    is_draft: bool | None = Field(default=None)


class ConfigUploadFile(BaseModel):
    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., description="Base64 encoded file content")

    def to_bytes(self) -> tuple[str, bytes]:
        return self.filename, base64.b64decode(self.content_base64)


class ConfigUploadParams(_BaseToolParams):
    config_type: str = Field(..., description="Configuration type")
    service: str | None = Field(default=None, description="Service identifier or global")
    files: list[ConfigUploadFile] = Field(..., min_length=1)
    is_draft: bool = Field(default=False, description="Create as draft")


class ConfigUploadUpdateParams(ConfigKeyParams):
    file: ConfigUploadFile = Field(...)
    new_service: str | None = Field(default=None)
    new_type: str | None = Field(default=None)
    new_name: str | None = Field(default=None)
    new_is_draft: bool | None = Field(default=None)


class ConfigsDeleteParams(_BaseToolParams):
    configs: list[ConfigKeyParams] = Field(..., min_length=1)


class PluginListParams(_BaseToolParams):
    type: str = Field(default="all", description="Plugin type filter")
    with_data: bool = Field(default=False)


class PluginUploadParams(_BaseToolParams):
    method: str = Field(default="ui", description="Installation method")
    files: list[ConfigUploadFile] = Field(..., min_length=1)


class PluginDeleteParams(_BaseToolParams):
    plugin_id: str = Field(..., min_length=1)


class CacheListParams(_BaseToolParams):
    service: str | None = Field(default=None)
    plugin: str | None = Field(default=None)
    job_name: str | None = Field(default=None)
    with_data: bool = Field(default=False)


class CacheFileKeyParams(_BaseToolParams):
    service: str | None = Field(default=None)
    plugin: str = Field(...)
    job_name: str = Field(...)
    file_name: str = Field(...)


class CacheDeleteBulkParams(_BaseToolParams):
    files: list[CacheFileKeyParams] = Field(..., min_length=1)


class CacheFetchParams(CacheFileKeyParams):
    download: bool = Field(default=False)


class JobDescriptor(BaseModel):
    plugin: str = Field(..., min_length=1)
    name: str | None = Field(default=None)


class JobsRunParams(_BaseToolParams):
    jobs: list[JobDescriptor] = Field(..., min_length=1, description="Jobs to execute")
