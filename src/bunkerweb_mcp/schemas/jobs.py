"""Schemas for scheduler job endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .common import ApiResponse


class JobItem(BaseModel):
    plugin: str = Field(..., description="Plugin identifier")
    name: str | None = Field(default=None, description="Job name")


class RunJobsRequest(BaseModel):
    jobs: list[JobItem] = Field(..., min_length=1, description="Jobs to trigger")


class JobsResponse(ApiResponse):
    data: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("data", "jobs"),
    )
