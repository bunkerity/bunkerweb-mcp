import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from bunkerweb_mcp.config import Settings
from bunkerweb_mcp.exceptions import ToolExecutionError
from bunkerweb_mcp.tools import Tools
from bunkerweb_mcp.tools.log_handlers import MAX_CONTENT_BYTES, MAX_SCAN_BYTES, LogReader
from bunkerweb_mcp.tools.params import EmptyParams, LogsReadParams


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_empty_logs_path_is_disabled() -> None:
    assert Settings(BUNKERWEB_LOGS_PATH="").bunkerweb_logs_path is None


@pytest.mark.asyncio
async def test_logs_list_allowlists_runtime_files(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write(root / "api.log", b"current\n")
    _write(root / "api.log.1", b"rotated\n")
    _write(root / "scheduler.log-2026-08-04", b"dated\n")
    _write(root / "api.log.2.gz", b"compressed\n")
    _write(root / "notes.txt", b"ignored\n")
    _write(root / "nested" / "worker.log", b"nested\n")
    _write(root / "letsencrypt" / "certbot.log.1", b"certificate\n")
    outside = tmp_path / "secret.log"
    _write(outside, b"secret\n")
    (root / "escape.log").symlink_to(outside)

    now = 1_800_000_000
    for index, path in enumerate(
        [root / "api.log", root / "api.log.1", root / "scheduler.log-2026-08-04"]
    ):
        os.utime(path, (now + index, now + index))

    result = await LogReader(root).list_logs(EmptyParams())

    sources = [item["source"] for item in result["data"]]
    assert sources == [
        "scheduler.log-2026-08-04",
        "api.log.1",
        "api.log",
        "letsencrypt/certbot.log.1",
    ]
    assert all(item["rotated"] for item in result["data"] if item["source"] != "api.log")


@pytest.mark.asyncio
async def test_logs_read_filters_and_paginates_without_overlap(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write(root / "api.log", b"INFO zero\nERROR one\ninfo two\nERROR three\nERROR four\n")
    reader = LogReader(root)

    first = await reader.read_logs(LogsReadParams(source="api.log", query="error", limit=2))
    second = await reader.read_logs(
        LogsReadParams(source="api.log", query="ERROR", limit=2, cursor=first["next_cursor"])
    )

    assert first["lines"] == ["ERROR three", "ERROR four"]
    assert first["has_more"] is True
    assert second["lines"] == ["ERROR one"]
    assert second["has_more"] is False


@pytest.mark.asyncio
async def test_logs_read_bounds_scan_and_output(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write(root / "api.log", b"old\n" + b"x" * (MAX_SCAN_BYTES + MAX_CONTENT_BYTES))

    result = await LogReader(root).read_logs(LogsReadParams(source="api.log"))

    assert result["scanned_bytes"] == MAX_SCAN_BYTES
    assert sum(len(line.encode()) for line in result["lines"]) <= MAX_CONTENT_BYTES
    assert result["content_truncated"] is True
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_logs_read_replaces_invalid_utf8_and_resets_large_cursor(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write(root / "api.log", b"valid\ninvalid:\xff\n")

    result = await LogReader(root).read_logs(LogsReadParams(source="api.log", cursor=10_000))

    assert result["lines"] == ["valid", "invalid:\ufffd"]
    assert result["cursor_reset"] is True


@pytest.mark.asyncio
async def test_log_tools_are_opt_in_and_reject_unknown_sources(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write(root / "api.log", b"safe\n")
    client = SimpleNamespace()

    assert Tools(client).get_tool("logs_list") is None  # type: ignore[arg-type]

    tools = Tools(client, logs_path=root)  # type: ignore[arg-type]
    assert tools.get_tool("logs_list") is not None
    read = tools.get_tool("logs_read")
    assert read is not None
    with pytest.raises(ToolExecutionError, match="Unknown log source"):
        await read({"source": "../secret.log"})


@pytest.mark.asyncio
async def test_logs_list_reports_missing_configured_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="logs directory not found"):
        await LogReader(tmp_path / "missing").list_logs(EmptyParams())
