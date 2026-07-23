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
    is_draft: bool = Field(False, description="Mark the configuration as draft")


class ConfigUpdateRequest(BaseModel):
    service: str | None = Field(default=None, description="New service identifier")
    type: str | None = Field(default=None, description="New configuration type")
    name: str | None = Field(default=None, description="New configuration name")
    data: str | None = Field(default=None, description="New configuration content")
    is_draft: bool | None = Field(default=None, description="Update draft state")


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
