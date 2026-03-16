"""Schemas for custom configuration endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .common import ApiResponse


class ConfigKey(BaseModel):
    service: str | None = Field(
        default=None,
        description="Service identifier or 'global'",
    )
    type: str = Field(..., min_length=1, description="Configuration type")
    name: str = Field(..., min_length=1, description="Configuration name")


class ConfigCreateRequest(BaseModel):
    service: str | None = Field(
        default=None,
        description="Service identifier or 'global'",
    )
    type: str = Field(..., min_length=1, description="Configuration type")
    name: str = Field(..., min_length=1, description="Configuration name")
    data: str = Field(..., description="Configuration content as UTF-8 text")


class ConfigUpdateRequest(BaseModel):
    new_service: str | None = Field(default=None, description="New service identifier")
    new_type: str | None = Field(default=None, description="New configuration type")
    new_name: str | None = Field(default=None, description="New configuration name")
    data: str | None = Field(default=None, description="New configuration content")


class ConfigsDeleteRequest(BaseModel):
    configs: list[ConfigKey] = Field(..., min_length=1, description="Configs to delete")


class ConfigResponse(ApiResponse):
    data: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "config"),
    )


class ConfigsResponse(ApiResponse):
    data: list[dict[str, Any]] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "configs"),
    )
