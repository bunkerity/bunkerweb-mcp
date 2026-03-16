"""Schemas for cache endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import ApiResponse


class CacheFileKey(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    service: str | None = Field(default=None, description="Service identifier")
    plugin: str = Field(..., description="Plugin identifier")
    job_name: str = Field(..., alias="jobName", description="Job name")
    file_name: str = Field(..., alias="fileName", description="File name")


class CacheFilesDeleteRequest(BaseModel):
    cache_files: list[CacheFileKey] = Field(..., min_length=1, description="Cache files to delete")


class CacheResponse(ApiResponse):
    data: list[dict[str, Any]] | None = None
