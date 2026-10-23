"""Tests for scripts/tdqs.py (no network, no tdqs download)."""

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from bunkerweb_mcp.tools.registry import TOOL_DESCRIPTIONS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tdqs.py"
LOG_TOOLS = {"logs_list", "logs_read"}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tdqs_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tdqs = _load()


def test_payload_matches_glama_tool_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The payload is the registry plus docs search, whatever the environment says."""
    monkeypatch.setenv("SEARCH_MODE", "disabled")
    monkeypatch.setenv("MCP_READ_ONLY", "true")
    monkeypatch.setenv("BUNKERWEB_LOGS_PATH", str(tmp_path))
    tools = asyncio.run(tdqs.build_tools())
    names = {tool["name"] for tool in tools}
    assert names == (set(TOOL_DESCRIPTIONS) - LOG_TOOLS) | {"search_bunkerweb_docs"}
    assert all(tool["description"] for tool in tools)
    assert all("inputSchema" in tool and "annotations" in tool for tool in tools)


def test_every_parameter_is_described() -> None:
    """TDQS lowers Parameter Semantics below 80% schema coverage; keep it at 100%."""
    tools = asyncio.run(tdqs.build_tools())
    missing = [
        f"{tool['name']}.{name}"
        for tool in tools
        for name, prop in tool["inputSchema"].get("properties", {}).items()
        if not prop.get("description")
    ]
    assert missing == []


def test_score_env_defaults_keep_caller_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tdqs.SCORE_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TDQS_MODEL", "custom-model")
    env = tdqs.tdqs_env("score", [])
    assert env["TDQS_MODEL"] == "custom-model"
    assert env["TDQS_BASE_URL"] == tdqs.SCORE_DEFAULTS["TDQS_BASE_URL"]


def test_custom_endpoint_gets_no_ollama_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tdqs.SCORE_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TDQS_BASE_URL", "https://openrouter.ai/api/v1")
    env = tdqs.tdqs_env("score", [])
    assert "TDQS_REQUEST_OVERRIDES" not in env
    assert "TDQS_MODEL" not in env


def test_lint_and_hosted_skip_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tdqs.SCORE_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    assert "TDQS_MODEL" not in tdqs.tdqs_env("lint", [])
    assert "TDQS_BASE_URL" not in tdqs.tdqs_env("score", ["--hosted", "https://tdqs.dev"])


def test_command_pins_tdqs_and_passes_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tdqs.shutil, "which", lambda _: "/usr/bin/uvx")
    command = tdqs.tdqs_command("score", Path("/tmp/t.json"), ["--fail-under", "B"])
    assert command[:4] == ["/usr/bin/uvx", "--from", f"tdqs=={tdqs.TDQS_VERSION}", "tdqs"]
    assert command[4:7] == ["score", "--file", "/tmp/t.json"]
    assert command[-2:] == ["--fail-under", "B"]
    assert "--concurrency" in command
    lint = tdqs.tdqs_command("lint", Path("/tmp/t.json"), [])
    assert "--concurrency" not in lint


def test_command_requires_uvx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tdqs.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit, match="uvx not found"):
        tdqs.tdqs_command("lint", Path("/tmp/t.json"), [])


def test_dump_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "tools.json"
    assert tdqs.main(["dump", "-o", str(out)]) == 0
    assert '"search_bunkerweb_docs"' in out.read_text()
