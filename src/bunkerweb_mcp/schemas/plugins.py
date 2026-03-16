"""Schemas for plugin management endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .common import ApiResponse


class PluginsResponse(ApiResponse):
    data: list[dict[str, Any]] | None = None


class PluginUploadDescriptor(BaseModel):
    filename: str
    content_base64: str
