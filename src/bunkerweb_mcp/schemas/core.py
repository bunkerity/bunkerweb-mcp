"""Schemas covering core endpoints."""

from typing import Any

from pydantic import BaseModel

from .common import ApiResponse


class PingResponse(ApiResponse):
    data: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str | None = None
    details: dict[str, Any] | None = None
