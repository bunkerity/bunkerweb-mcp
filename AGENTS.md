# Repository Guidelines

This is the only agent guide for the repository. `CLAUDE.md` imports it; edit this file, not
`CLAUDE.md`. It is for people and agents who change this code. To operate a BunkerWeb
deployment through the server, read the bundled `bunkerweb` skill
(`skill://bunkerweb/bunkerweb/SKILL.md`) instead.

## What this repository is

An MCP server that wraps the BunkerWeb API. It runs as a FastAPI app with a streamable HTTP
MCP endpoint, or as a stdio server (`bunkerweb-mcp` console script). It holds no BunkerWeb
state: a tool call becomes a REST call to the API at `BUNKERWEB_BASE_URL` (default
`http://localhost:8888`), and BunkerWeb applies the change itself. The client retries
transient errors with backoff. Three exceptions:

- Reads of services, instances, global config and bans come from an in-memory cache
  (`cache.py`, TTL 30 s to 10 min) while `CACHE_ENABLED` is true, its default.
- `logs_list` and `logs_read` read local files under `BUNKERWEB_LOGS_PATH`
  (`tools/log_handlers.py`) and make no API call.
- `search_bunkerweb_docs` calls the separate search service (`search_client.py`).

## Project Structure & Module Organization

Application code uses a `src/` layout under `src/bunkerweb_mcp/`:

- `main.py` builds the FastAPI app: MCP at `/mcp`, plus `/tools`, `/rpc`, `/ws`, `/metrics`,
  `/health` and `/ready`. `cli.py` is the stdio entry point.
- `mcp_adapter.py` registers tools, prompts and resources on the MCP server.
- `client.py` is the async HTTPX client for the BunkerWeb API.
- `tools/` holds the handlers (`*_handlers.py`), the Pydantic parameter models (`params.py`)
  and the registry (`registry.py`, where `TOOL_DESCRIPTIONS` lists every tool).
- `config.py` holds the `Settings` class; `.env.example` documents each variable.
- `search_client.py`, `skill_catalog.py`, `prompt_catalog.py`, `cache.py`, `rate_limiter.py`,
  `metrics.py` and `tracing.py` support the above.
- `data/tool_prompts.json` holds the per-tool prompts; `data/skills/` holds the vendored skills.

Tests live in `tests/` as `test_*.py` modules. Docs and ADRs are in `docs/`; deployment assets
are in `deploy/` and the root Compose files; n8n examples are in `n8n-workflows/`.

## What the server exposes

- **Tools** (43 by default, from `TOOL_DESCRIPTIONS`): core (`authenticate`, `ping`, `health`), instances,
  bans, services, global config, custom configs, plugins, cache and jobs. `logs_list` and
  `logs_read` register only when `BUNKERWEB_LOGS_PATH` is set. `search_bunkerweb_docs`
  registers only when `SEARCH_MODE=remote`.
- **Resources**: `config://global`, `logs://jobs`, `bans://active`, `instances://status`
  (JSON), and `skill://bunkerweb/<skill>/<path>` for the vendored skills when
  `MCP_ENABLE_SKILLS=true`.
- **Prompts**: one per tool that has text in `data/tool_prompts.json`; override the file with
  `BUNKERWEB_PROMPT_CATALOG`.
- **Search**: `search_bunkerweb_docs` calls an external search service at `SEARCH_API_URL`
  (see `docs/adr/0002-externalize-search-service.md`). The server holds no index or model.

New tool: add the handler and `Params` model under `tools/`, register it in `registry.py`
(entry in `_registry` and in `TOOL_DESCRIPTIONS`), and cover it in `tests/`.

## Authentication & Configuration

Settings come from environment variables or `.env` (`config.py`; copy `.env.example`).
Secrets are `SecretStr` and masked in logs; read them through the `get_*` accessors and never
log the result. Beware two defaults: `config.py` defaults `SEARCH_MODE` to `remote`
(`SEARCH_API_URL=http://localhost:8000`), the Dockerfile sets the same, and `.env.example` and
the Compose files set `disabled`.

| Endpoint | Application check |
| --- | --- |
| `/mcp/` | `x-mcp-token` header, only when `BUNKERWEB_LOGS_PATH` is set (startup fails if the token is empty) |
| `/rpc` | `x-mcp-token` header when `BUNKERWEB_WEBSOCKET_TOKEN` is set |
| `/ws` | `token` query parameter when `BUNKERWEB_WEBSOCKET_TOKEN` is set |
| `/tools`, `/health`, `/ready`, `/metrics` | none |

Token comparison goes through `_token_matches` (constant time, bytes). `BUNKERWEB_API_TOKEN` or
Basic credentials authenticate the server to BunkerWeb, not clients to the server; a bearer
token wins over Basic. The server has no per-client roles or read-only mode, and several tools
change or delete BunkerWeb state (`delete_service`, `instance_stop`, `plugins_upload`,
`unban_ip`, ...). Keep that in mind when adding tools or changing authentication.

`BUNKERWEB_REDACT_SECRETS` masks by setting name in registry tool results and withholds upstream error details; logs, custom config text and docs search are outside it (`docs/security.md`, "Secret Redaction"). Build any API path from `client._segment`, never a raw f-string.

## Build, Test, and Development Commands

Use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes --no-deps -r requirements-build.txt
pip install --require-hashes --no-deps -r requirements-dev.txt
pip install --no-deps --no-build-isolation -e .
```

Run `pytest` for the full suite and coverage. Use `ruff check src/ tests/ scripts/` to lint,
`ruff format --check src/ tests/ scripts/` to verify formatting, and `mypy src/ --strict` for
type checking. Start locally with
`uvicorn bunkerweb_mcp.main:app --reload --port 8080`, or run the container stack with
`docker compose up --build`. `scripts/check-all.sh` only checks and never reformats or fixes
source files: it runs `pytest tests/`, `ruff format --check src/bunkerweb_mcp/`,
`ruff check src/bunkerweb_mcp/` and `mypy src/ --strict`, and stops at the first failure
(`set -e`). It does not lint `tests/` or `scripts/`; run the `ruff` commands above for those.

### Refreshing the lock files

Each lock has a source file with exact pins: `requirements-build.in` -> `requirements-build.txt`,
`requirements.in` -> `requirements.txt` and `requirements-dev.in` (which starts with
`-r requirements.in`) -> `requirements-dev.txt`. The locks are hash-pinned and generated with
uv. Edit the `.in` file (and keep the `pyproject.toml` ranges compatible), then re-run the three
commands; never hand-edit a `.txt` lock:

```bash
uv pip compile --universal --python-version 3.11 --generate-hashes requirements-build.in -o requirements-build.txt
uv pip compile --universal --python-version 3.11 --generate-hashes requirements.in -o requirements.txt
uv pip compile --universal --python-version 3.11 --generate-hashes --constraint requirements.txt requirements-dev.in -o requirements-dev.txt
```

Bump one package with `--upgrade-package <name>` on each command that locks it. Dependabot's
`pip` updater bumps `.in`/`.txt` pairs with interpreter-specific `pip-compile`, not uv, so a
Dependabot PR that touches `requirements*.txt` is never merged as-is: on its branch, the human
regenerates the locks with the uv commands above (`--upgrade-package <name>`) and pushes. CI
(`tests/test_locks.py` on 3.11–3.14, plus the arm64 image build) is the backstop.

## Coding Style & Naming Conventions

Use four-space indentation, Python 3.11 type syntax, and explicit return types. Ruff
enforces 100-character formatting, import order, naming, pyupgrade, and bugbear rules.
Use `snake_case` for modules, functions, and variables; `PascalCase` for classes and
Pydantic models; and `UPPER_SNAKE_CASE` for constants and environment variables. New
tool handlers need Google-style docstrings and should reuse shared parameter and
schema helpers.

## Testing Guidelines

Pytest runs with asyncio support and an 80% coverage floor. Name tests
`test_<behavior>` and mark async tests appropriately. Mock BunkerWeb and network calls;
cover success, validation, authentication, and upstream-failure paths for changed
handlers. Run a focused test first, for example `pytest tests/test_client.py -q`, then
the full suite.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects, usually with a Conventional Commits prefix
(`fix:`, `feat:`, `ci:`, `chore:`, `build(deps):`); the prefix is not enforced. Keep each
commit scoped. PRs should explain behavior and risk, link the issue when applicable, list
verification commands, and note configuration or ADR changes. Include screenshots only when
dashboards or n8n workflows change. `pre-commit run --all-files` checks YAML/TOML, file
hygiene, and Ruff.

## Security & Configuration

Copy `.env.example` to `.env`; never commit tokens, passwords, or real endpoint
credentials. Preserve validation and authentication boundaries when adding tools.
Record architectural changes in `docs/adr/`. HTTP deployment guidance is in
`docs/security.md`; metrics, tracing and dashboards are in `docs/OBSERVABILITY.md`.

## Vendored Skills

`src/bunkerweb_mcp/data/skills/` is a byte-for-byte copy of the `skills/` tree of
`bunkerity/bunkerweb-skills`, pinned by the commit in `SKILLS_REF`. Never edit it by hand;
formatters skip it. To bump: `python scripts/sync_skills.py --ref <40-hex sha>`. CI runs
`python scripts/sync_skills.py --check` and fails on any drift.

The `bunkerweb` skill is the operator guide for BunkerWeb itself (configuration, ModSecurity
and CRS, antibot, bans, jobs, troubleshooting, migration); the server's `instructions` point
clients to it. Do not duplicate that guidance in this file.
