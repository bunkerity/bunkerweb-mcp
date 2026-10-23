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
    from ..schemas.plugins import PluginsResponse
    from ..schemas.services import ServiceResponse, ServicesResponse


@runtime_checkable
class BunkerWebClientProtocol(Protocol):
    """Protocol defining the interface for BunkerWeb API client."""

    @property
    def base_url(self) -> str: ...

    async def get_openapi_version(self) -> str | None: ...

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

    async def list_plugins(self, *, plugin_type: str, with_data: bool) -> PluginsResponse: ...

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


class DiagnoseParams(_BaseToolParams):
    service: str | None = Field(
        default=None,
        description="Optional service ID (its first SERVER_NAME) to also check existence, draft state and setting owners",
    )


class ReloadParams(_BaseToolParams):
    test: bool = Field(
        True,
        description="Test the configuration first and reload only if the test passes; this still reloads, it is not a dry run.",
    )


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
    hostname: str = Field(
        ..., description="Hostname or IP the scheduler uses to reach the instance API"
    )
    name: str | None = Field(default=None, description="Friendly instance name")
    port: int | None = Field(
        default=None, ge=1, le=65535, description="Instance API HTTP port (API_HTTP_PORT)"
    )
    listen_https: bool | None = Field(
        default=None, description="Whether the instance API is reached over HTTPS"
    )
    https_port: int | None = Field(
        default=None, ge=1, le=65535, description="Instance API HTTPS port"
    )
    server_name: str | None = Field(
        default=None, description="Host header sent to the instance API (API_SERVER_NAME)"
    )
    method: str | None = Field(
        default=None, description="Source method tag recorded on the instance"
    )


class InstanceUpdateParams(_BaseToolParams):
    hostname: str = Field(..., description="Hostname of the registered instance to update")
    name: str | None = Field(default=None, description="New friendly name; omit to keep")
    port: int | None = Field(
        default=None, ge=1, le=65535, description="New instance API HTTP port; omit to keep"
    )
    listen_https: bool | None = Field(
        default=None, description="Reach the instance API over HTTPS; omit to keep"
    )
    https_port: int | None = Field(
        default=None, ge=1, le=65535, description="New instance API HTTPS port; omit to keep"
    )
    server_name: str | None = Field(
        default=None, description="New Host header for the instance API; omit to keep"
    )
    method: str | None = Field(default=None, description="New source method tag; omit to keep")


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
    variables: dict[str, str] | None = Field(
        default=None,
        description="Unprefixed per-service setting names and values; unknown or externally owned names are skipped and reported.",
    )


class ServiceConvertParams(_BaseToolParams):
    service: str = Field(..., description="Service identifier")
    convert_to: str = Field(..., pattern="^(online|draft)$", description="Target state")


class GlobalConfigReadParams(_BaseToolParams):
    full: bool = Field(default=False, description="Include defaulted settings")
    methods: bool = Field(default=False, description="Include method metadata")


class GlobalConfigUpdateParams(_BaseToolParams):
    config: dict[str, Any] = Field(..., description="Key-value pairs to update")


_CONFIG_TYPE_HELP = (
    "Custom config type, e.g. http, server-http, default-server-http, stream, server-stream, "
    "modsec, modsec-crs, crs-plugins-before, crs-plugins-after"
)


class ConfigListParams(_BaseToolParams):
    service: str | None = Field(
        default=None,
        description="Filter by service ID; omit or 'global' to list every scope, global included",
    )
    type: str | None = Field(default=None, description=f"Filter by type. {_CONFIG_TYPE_HELP}")
    with_drafts: bool = Field(default=True, description="Include snippets of draft services")
    with_data: bool = Field(
        default=False, description="Include each snippet's content; false returns metadata only"
    )


class ConfigKeyParams(_BaseToolParams):
    service: str | None = Field(
        default=None, description="Service ID that owns the snippet; omit or 'global' for global"
    )
    type: str = Field(..., description=_CONFIG_TYPE_HELP)
    name: str = Field(..., description="Snippet name: letters, digits, _ or -, no extension")


class ConfigCreateParams(ConfigKeyParams):
    data: str = Field(..., description="Configuration content")
    is_draft: bool = Field(default=False, description="Create as draft")


class ConfigUpdateParams(ConfigKeyParams):
    new_service: str | None = Field(default=None, description="Move to this service; omit to keep")
    new_type: str | None = Field(default=None, description="Change the type; omit to keep")
    new_name: str | None = Field(default=None, description="Rename the snippet; omit to keep")
    data: str | None = Field(default=None, description="New snippet content; omit to keep")
    is_draft: bool | None = Field(default=None, description="Set the draft flag; omit to keep")


class ConfigUploadFile(BaseModel):
    filename: str = Field(..., min_length=1, description="File name, with its extension")
    content_base64: str = Field(..., description="Base64 encoded file content")

    def to_bytes(self) -> tuple[str, bytes]:
        return self.filename, base64.b64decode(self.content_base64)


class ConfigUploadParams(_BaseToolParams):
    config_type: str = Field(..., description=f"Type for every uploaded file. {_CONFIG_TYPE_HELP}")
    service: str | None = Field(
        default=None, description="Service ID for every file; omit or 'global' for global"
    )
    files: list[ConfigUploadFile] = Field(
        ...,
        min_length=1,
        description="Files to create, one snippet per file, named after the sanitized file stem",
    )
    is_draft: bool = Field(default=False, description="Create as draft")


class ConfigUploadUpdateParams(ConfigKeyParams):
    file: ConfigUploadFile = Field(..., description="File whose content replaces the snippet's")
    new_service: str | None = Field(default=None, description="Move to this service; omit to keep")
    new_type: str | None = Field(default=None, description="Change the type; omit to keep")
    new_name: str | None = Field(
        default=None,
        description="New name; if omitted the file stem renames the snippet, so pass the current name to keep it",
    )
    new_is_draft: bool | None = Field(default=None, description="Set the draft flag; omit to keep")


class ConfigsDeleteParams(_BaseToolParams):
    configs: list[ConfigKeyParams] = Field(
        ..., min_length=1, description="Snippets to delete, each by service, type and name"
    )


class PluginListParams(_BaseToolParams):
    type: str = Field(default="all", description="Plugin type filter: all, external, ui or pro")
    with_data: bool = Field(default=False, description="Include each plugin's archive data")


class PluginUploadParams(_BaseToolParams):
    method: str = Field(default="ui", description="Installation method; the API supports only ui")
    files: list[ConfigUploadFile] = Field(
        ..., min_length=1, description="Plugin archives (.zip, .tar.gz or .tar.xz), base64 encoded"
    )


class PluginDeleteParams(_BaseToolParams):
    plugin_id: str = Field(
        ..., min_length=1, description="ID of a UI plugin, as returned by plugins_list type=ui"
    )


class CacheListParams(_BaseToolParams):
    service: str | None = Field(
        default=None,
        description="Filter by service ID; omit or 'global' to list every scope, global included",
    )
    plugin: str | None = Field(default=None, description="Filter by plugin ID, e.g. letsencrypt")
    job_name: str | None = Field(default=None, description="Filter by job name")
    with_data: bool = Field(
        default=False, description="Include text file contents inline; false returns metadata only"
    )


class CacheFileKeyParams(_BaseToolParams):
    service: str | None = Field(
        default=None, description="Service ID that owns the file; omit for global"
    )
    plugin: str = Field(..., description="Plugin ID that owns the file, as listed by cache_list")
    job_name: str = Field(..., description="Job that wrote the file, as listed by cache_list")
    file_name: str = Field(..., description="File name, as listed by cache_list")


class CacheDeleteBulkParams(_BaseToolParams):
    files: list[CacheFileKeyParams] = Field(
        ..., min_length=1, description="Cache files to delete, each keyed as in cache_list"
    )


class CacheFetchParams(CacheFileKeyParams):
    download: bool = Field(
        default=False,
        description="True returns the raw bytes as data_base64; false returns JSON with printable text only",
    )


class JobDescriptor(BaseModel):
    plugin: str = Field(..., min_length=1, description="Plugin ID that owns the job")
    name: str | None = Field(
        default=None, description="Job name; informational, the API triggers the plugin's jobs"
    )


class JobsRunParams(_BaseToolParams):
    jobs: list[JobDescriptor] = Field(..., min_length=1, description="Jobs to execute")


class LogsReadParams(_BaseToolParams):
    source: str = Field(..., min_length=1, max_length=255, description="Source from logs_list")
    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        description="Optional case-insensitive literal text filter",
    )
    limit: int = Field(default=100, ge=1, le=500, description="Maximum matching lines")
    cursor: int | None = Field(
        default=None,
        ge=0,
        description="Byte cursor returned by a previous logs_read call",
    )
