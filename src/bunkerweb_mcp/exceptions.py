"""Custom exception types used throughout the MCP server."""


class BunkerWebError(Exception):
    """Base exception for BunkerWeb client errors."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ToolValidationError(Exception):
    """Raised when tool input validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
