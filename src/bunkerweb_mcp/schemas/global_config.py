"""Schemas for global configuration endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .common import ApiResponse


class GlobalConfigResponse(ApiResponse):
    data: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "config"),
    )


class GlobalConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
