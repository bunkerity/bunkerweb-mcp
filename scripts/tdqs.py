#!/usr/bin/env python3
"""Score this server's tool definitions with TDQS, the rubric behind Glama's quality grade.

    python scripts/tdqs.py lint                    # deterministic checks, no model, offline
    python scripts/tdqs.py score                   # full rubric through an OpenAI-compatible model
    python scripts/tdqs.py dump -o tools.json      # write the tools/list payload only

Run it with the project virtualenv. Arguments after the subcommand go to the `tdqs` CLI
(`--format markdown`, `--output report.json`, `--fail-under B`, `--hosted https://tdqs.dev`).
The tools/list payload matches what Glama scores: the 44 registry tools plus
`search_bunkerweb_docs`, without the log tools, whatever `.env` or the environment says.

`score` defaults to the free `gpt-oss:20b-cloud` model through a local Ollama signed in to
ollama.com; the model runs remotely and loads nothing into local memory. Set TDQS_BASE_URL,
TDQS_API_KEY and TDQS_MODEL for another endpoint. Scores are calibrated to a rubric and model
pair, so compare runs made with the same model only; see docs/tdqs.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TDQS_VERSION = "0.1.0"
SERVER_NAME = "bunkerweb-mcp"
SCORE_DEFAULTS = {
    "TDQS_BASE_URL": "http://localhost:11434/v1",
    "TDQS_API_KEY": "ollama",
    "TDQS_MODEL": "gpt-oss:20b-cloud",
    "TDQS_REQUEST_OVERRIDES": '{"think": false, "reasoning_effort": "low"}',
}


async def build_tools() -> list[dict[str, Any]]:
    """Return the tools/list payload of the server as Glama builds it."""
    from bunkerweb_mcp.client import BunkerWebClient
    from bunkerweb_mcp.config import Settings
    from bunkerweb_mcp.mcp_adapter import create_fastmcp_server
    from bunkerweb_mcp.tools import Tools

    settings = Settings(
        _env_file=None,
        search_mode="remote",
        bunkerweb_logs_path=None,
        read_only=False,
        skills_enabled=False,
        redact_secrets=False,
    )
    client = BunkerWebClient(settings=settings)
    try:
        server = create_fastmcp_server(settings, Tools(client))
        tools = await server.list_tools()
    finally:
        await client.close()
    return [tool.model_dump(by_alias=True, exclude_none=True, mode="json") for tool in tools]


def tdqs_command(mode: str, tools_file: Path, extra: list[str]) -> list[str]:
    """Build the pinned `tdqs` invocation for one subcommand."""
    uvx = shutil.which("uvx")
    if uvx is None:
        raise SystemExit("uvx not found: install uv (https://docs.astral.sh/uv/)")
    command = [uvx, "--from", f"tdqs=={TDQS_VERSION}", "tdqs", mode, "--file", str(tools_file)]
    command += ["--server-name", SERVER_NAME]
    if mode == "score" and "--concurrency" not in extra:
        command += ["--concurrency", "2"]
    return command + extra


def tdqs_env(mode: str, extra: list[str]) -> dict[str, str]:
    """Return the environment for `tdqs`, with the calibrated Ollama model unless one is set.

    The defaults fill only what the caller left unset, and only when TDQS_BASE_URL is unset:
    the request overrides are Ollama-specific and a stricter provider may reject them.
    """
    env = dict(os.environ)
    if mode == "score" and "--hosted" not in extra and "TDQS_BASE_URL" not in env:
        for key, value in SCORE_DEFAULTS.items():
            env.setdefault(key, value)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("mode", choices=("lint", "score", "dump"))
    parser.add_argument("-o", "--tools-out", type=Path, help="also keep the tools/list JSON here")
    args, extra = parser.parse_known_args(argv)

    payload = json.dumps({"tools": asyncio.run(build_tools())}, indent=2) + "\n"
    if args.tools_out:
        args.tools_out.write_text(payload)
    if args.mode == "dump":
        if not args.tools_out:
            sys.stdout.write(payload)
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tools_file = Path(tmp) / "tools.json"
        tools_file.write_text(payload)
        command = tdqs_command(args.mode, tools_file, extra)
        return subprocess.run(command, env=tdqs_env(args.mode, extra), check=False).returncode  # noqa: S603


if __name__ == "__main__":
    sys.exit(main())
