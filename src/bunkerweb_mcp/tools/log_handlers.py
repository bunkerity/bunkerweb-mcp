"""Bounded read-only access to local BunkerWeb log files."""

from __future__ import annotations

import os
import re
import stat
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..exceptions import ToolExecutionError
from .params import EmptyParams, LogsReadParams

MAX_SCAN_BYTES = 1024 * 1024
MAX_CONTENT_BYTES = 64 * 1024
LOG_NAME = re.compile(r"^.+\.log(?:[.-]\d.*)?$")


def _modified_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


class LogReader:
    """List and query a configured BunkerWeb log directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def _inventory(self) -> dict[str, tuple[Path, os.stat_result]]:
        if not self._root.is_dir():
            raise FileNotFoundError(f"BunkerWeb logs directory not found: {self._root}")

        files: dict[str, tuple[Path, os.stat_result]] = {}
        directories = [self._root]
        letsencrypt = self._root / "letsencrypt"
        if letsencrypt.is_dir():
            directories.append(letsencrypt)

        for directory in directories:
            for path in directory.iterdir():
                if (
                    path.is_symlink()
                    or path.name.endswith(".gz")
                    or LOG_NAME.fullmatch(path.name) is None
                    or not path.is_file()
                ):
                    continue
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(self._root):
                    continue
                file_stat = resolved.stat()
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                files[resolved.relative_to(self._root).as_posix()] = (resolved, file_stat)
        return files

    async def list_logs(self, params: EmptyParams) -> dict[str, Any]:
        """List readable active and uncompressed rotated logs."""
        del params
        return self._list_logs()

    def _list_logs(self) -> dict[str, Any]:
        sources = [
            {
                "source": source,
                "size": file_stat.st_size,
                "modified_at": _modified_at(file_stat.st_mtime),
                "rotated": not source.endswith(".log"),
            }
            for source, (_, file_stat) in self._inventory().items()
        ]
        sources.sort(key=lambda item: (str(item["modified_at"]), str(item["source"])), reverse=True)
        return {"status": "success", "data": sources}

    async def read_logs(self, params: LogsReadParams) -> dict[str, Any]:
        """Read a bounded window from one allowlisted log source."""
        return self._read_logs(params)

    def _read_logs(self, params: LogsReadParams) -> dict[str, Any]:
        entry = self._inventory().get(params.source)
        if entry is None:
            raise ToolExecutionError(f"Unknown log source: {params.source}")
        path, _ = entry

        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as log_file:
            file_stat = os.fstat(log_file.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise ToolExecutionError(f"Log source is not a regular file: {params.source}")

            size = file_stat.st_size
            cursor_reset = params.cursor is not None and params.cursor > size
            end = size if params.cursor is None else min(params.cursor, size)
            window_start = max(0, end - MAX_SCAN_BYTES)
            log_file.seek(window_start)
            content = log_file.read(end - window_start)

            if end < size and end > 0:
                log_file.seek(end - 1)
                if log_file.read(1) != b"\n":
                    last_newline = content.rfind(b"\n")
                    content = b"" if last_newline < 0 else content[: last_newline + 1]

        content_start = window_start
        partial_window = False
        if window_start > 0 and content:
            first_newline = content.find(b"\n")
            if first_newline < 0:
                partial_window = True
            else:
                content_start += first_newline + 1
                content = content[first_newline + 1 :]

        query = params.query.casefold() if params.query else None
        matches: deque[tuple[int, str]] = deque(maxlen=params.limit)
        matched_in_window = 0
        position = content_start
        for raw_line in content.splitlines(keepends=True):
            line_start = position
            position += len(raw_line)
            text = raw_line.rstrip(b"\r\n").decode("utf-8", errors="replace")
            if query is None or query in text.casefold():
                matched_in_window += 1
                matches.append((line_start, text))

        selected = list(matches)
        kept_reversed: list[tuple[int, str]] = []
        content_bytes = 0
        content_truncated = partial_window
        for offset, text in reversed(selected):
            encoded = text.encode("utf-8")
            remaining = MAX_CONTENT_BYTES - content_bytes
            if len(encoded) > remaining:
                content_truncated = True
                if not kept_reversed and remaining > 0:
                    text = encoded[:remaining].decode("utf-8", errors="ignore")
                    kept_reversed.append((offset, text))
                break
            kept_reversed.append((offset, text))
            content_bytes += len(encoded)

        kept = list(reversed(kept_reversed))
        has_older_content = content_start > 0
        has_more = has_older_content or matched_in_window > len(selected) or content_truncated
        next_cursor = (kept[0][0] if kept else content_start) if has_more else None

        return {
            "status": "success",
            "source": params.source,
            "file_size": size,
            "modified_at": _modified_at(file_stat.st_mtime),
            "lines": [text for _, text in kept],
            "count": len(kept),
            "scanned_bytes": end - window_start,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "content_truncated": content_truncated,
            "cursor_reset": cursor_reset,
        }
