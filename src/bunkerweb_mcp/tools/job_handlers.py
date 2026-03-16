"""Job management handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..schemas.jobs import JobItem, RunJobsRequest

if TYPE_CHECKING:
    from .params import BunkerWebClientProtocol, EmptyParams, JobsRunParams


def _serialize_response(response: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic response model to dict."""
    return response.model_dump(mode="json", exclude_none=True)


async def handle_list_jobs(client: BunkerWebClientProtocol, params: EmptyParams) -> dict[str, Any]:
    """List scheduler jobs and history."""
    response = await client.list_jobs()
    return _serialize_response(response)


async def handle_run_jobs(client: BunkerWebClientProtocol, params: JobsRunParams) -> dict[str, Any]:
    """Trigger one or more scheduler jobs."""
    jobs = [JobItem(plugin=job.plugin, name=job.name) for job in params.jobs]
    request = RunJobsRequest(jobs=jobs)
    response = await client.run_jobs(request)
    return _serialize_response(response)
