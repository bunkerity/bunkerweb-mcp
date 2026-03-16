"""Schemas for bans endpoints."""

from typing import Any

from pydantic import BaseModel, Field, IPvAnyAddress

from .common import ApiResponse


class BanRequestModel(BaseModel):
    """Payload to ban an IP across BunkerWeb instances."""

    ip: IPvAnyAddress = Field(..., description="IP address to ban")
    exp: int = Field(
        default=86400,
        ge=0,
        description="Expiration in seconds (0 means permanent).",
    )
    reason: str = Field(
        default="api",
        description="Short reason for audit logs.",
        max_length=255,
    )
    service: str | None = Field(
        default=None,
        description="Optional service identifier (use None for global ban).",
    )


class UnbanRequestModel(BaseModel):
    """Payload to unban an IP."""

    ip: IPvAnyAddress = Field(..., description="IP address to unban")
    service: str | None = Field(
        default=None,
        description="Optional service identifier (use None for global scope).",
    )


class BansResponse(ApiResponse):
    """Nominal response returned by bans endpoints."""

    data: Any | None = None
