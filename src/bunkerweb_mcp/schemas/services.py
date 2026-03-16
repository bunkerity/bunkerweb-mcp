"""Schemas for service-related endpoints."""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .common import ApiResponse


class ServiceCreateRequest(BaseModel):
    server_name: str = Field(..., description="Primary server name for the service")
    is_draft: bool = Field(False, description="Whether the service is created as draft")
    variables: dict[str, str] | None = Field(default=None, description="Service variables")


class ServiceUpdateRequest(BaseModel):
    server_name: str | None = Field(
        default=None, description="New primary server name for the service"
    )
    is_draft: bool | None = Field(default=None, description="Toggle draft/online status")
    variables: dict[str, str] | None = Field(default=None, description="Variables to upsert")


class ServiceResponse(ApiResponse):
    service: Any | None = Field(
        default=None,
        description="Service identifier or payload",
        validation_alias=AliasChoices("service", "id"),
    )
    data: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "config"),
    )


class ServicesResponse(ApiResponse):
    data: list[dict[str, Any]] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "services"),
    )
