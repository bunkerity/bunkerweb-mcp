"""Schemas for instances endpoints."""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .common import ApiResponse


class InstanceCreateRequest(BaseModel):
    hostname: str = Field(..., description="Instance hostname")
    name: str | None = Field(None, description="Friendly name for the instance")
    port: int | None = Field(None, ge=1, le=65535, description="HTTP port")
    listen_https: bool | None = Field(None, description="Whether the instance listens on HTTPS")
    https_port: int | None = Field(None, ge=1, le=65535, description="HTTPS port if enabled")
    server_name: str | None = Field(
        None, description="Server name/Host header used to contact the instance"
    )
    method: str | None = Field(None, description="Source method tag")


class InstanceUpdateRequest(BaseModel):
    name: str | None = Field(None, description="Friendly name for the instance")
    port: int | None = Field(None, ge=1, le=65535, description="HTTP port")
    listen_https: bool | None = Field(None, description="Whether the instance listens on HTTPS")
    https_port: int | None = Field(None, ge=1, le=65535, description="HTTPS port if enabled")
    server_name: str | None = Field(
        None, description="Server name/Host header used to contact the instance"
    )
    method: str | None = Field(None, description="Source method tag")


class InstancesDeleteRequest(BaseModel):
    instances: list[str] = Field(..., min_length=1, description="Hostnames to delete")


class InstancesResponse(ApiResponse):
    data: list[dict[str, Any]] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "instances"),
    )
