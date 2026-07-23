"""Schemas for plugin management endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .common import ApiResponse


class PluginsResponse(ApiResponse):
    data: list[dict[str, Any]] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "plugins"),
    )


class PluginUploadDescriptor(BaseModel):
    filename: str
    content_base64: str
