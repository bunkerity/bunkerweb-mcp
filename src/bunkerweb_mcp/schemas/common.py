"""Common data structures shared across schemas."""

from typing import Any

from pydantic import BaseModel

JsonDict = dict[str, Any]


class ApiResponse(BaseModel):
    """Generic shape returned by the BunkerWeb API."""

    status: str | None = None
    message: str | None = None
    data: Any | None = None

    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "allow",
    }
