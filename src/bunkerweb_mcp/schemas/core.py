"""Schemas covering core endpoints."""

from typing import Any

from .common import ApiResponse


class PingResponse(ApiResponse):
    data: dict[str, Any] | None = None


class AuthResponse(ApiResponse):
    token: str
