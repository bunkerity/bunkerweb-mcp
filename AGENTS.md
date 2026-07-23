# Repository Guidelines

## Project Structure & Module Organization

Application code uses a `src/` layout under `src/bunkerweb_mcp/`. `main.py` builds the
FastAPI/MCP server, `cli.py` provides the console entry point, `client.py` talks to
BunkerWeb, `tools/` contains tool handlers and their registry, and `schemas/` holds
Pydantic models. Tests live in `tests/` as `test_*.py` modules. Runtime prompt data is
in `prompts/`; architecture decisions and operational guidance live in `docs/`;
deployment assets are under `deploy/` and the root Compose files. n8n examples belong
in `n8n-workflows/`.

## Build, Test, and Development Commands

Use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

Run `pytest` for the full suite and coverage. Use `ruff check src/ tests/` to lint,
`ruff format --check src/ tests/` to verify formatting, and `mypy src/ --strict` for
type checking. Start locally with
`uvicorn bunkerweb_mcp.main:app --reload --port 8080`, or run the container stack with
`docker compose up --build`. `scripts/check-all.sh` runs the checks but also formats
source files, so review its diff.

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

History favors short, imperative subjects, such as `Fix stdio docs for VS Code`. Keep
each commit scoped; Conventional Commits are not required. PRs should explain behavior
and risk, link the issue when applicable, list verification commands, and note
configuration or ADR changes. Include screenshots only when dashboards or n8n
workflows change.

## Security & Configuration

Copy `.env.example` to `.env`; never commit tokens, passwords, or real endpoint
credentials. Preserve validation and authentication boundaries when adding tools.
Record architectural changes in `docs/adr/`.
