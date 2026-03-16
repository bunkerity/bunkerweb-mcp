"""Logging utilities for the MCP server."""

import json
import logging
from typing import Any


class JsonFormatter(logging.Formatter):
    """A compact JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        safe_extra = getattr(record, "metrics", None)
        if isinstance(safe_extra, dict):
            payload.setdefault("metrics", safe_extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in payload:
                continue
            if key in {"args", "msg", "message"}:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging handler for the application."""

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    # Avoid duplicate handlers when reloading
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
