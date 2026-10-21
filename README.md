<p align="center">
  <a href="https://www.bunkerweb.io">
    <img alt="BunkerWeb logo" src="https://github.com/bunkerity/bunkerweb/raw/v1.6.17-rc1/misc/logo.png" width="350" />
  </a>
</p>

<h1 align="center">BunkerWeb MCP Server</h1>

<p align="center">
  Expose the BunkerWeb API to MCP clients through tools, read-only resources, and tool guidance prompts.
</p>

<p align="center">
  <a href="https://github.com/bunkerity/bunkerweb-mcp/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/bunkerity/bunkerweb-mcp/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="https://score.getplumber.io/github.com/bunkerity/bunkerweb-mcp"><img alt="Plumber CI/CD security score" src="https://score.getplumber.io/github.com/bunkerity/bunkerweb-mcp.svg" /></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/bunkerity/bunkerweb-mcp"><img alt="OpenSSF Scorecard" src="https://api.securityscorecards.dev/projects/github.com/bunkerity/bunkerweb-mcp/badge" /></a>
  <a href="https://glama.ai/mcp/servers/bunkerity/bunkerweb-mcp"><img alt="Glama MCP server score" src="https://glama.ai/mcp/servers/bunkerity/bunkerweb-mcp/badges/score.svg" /></a>
  <a href="https://hub.docker.com/r/bunkerity/bunkerweb-mcp"><img alt="Docker pulls" src="https://img.shields.io/docker/pulls/bunkerity/bunkerweb-mcp" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg" /></a>
</p>

<p align="center">
  <a href="https://www.bunkerweb.io">Website</a> &#124;
  <a href="https://docs.bunkerweb.io">BunkerWeb documentation</a> &#124;
  <a href="#quick-start">Quick start</a> &#124;
  <a href="#connect-an-mcp-client">Client setup</a>
</p>

Manage services, instances, bans, configuration snippets, plugins, and scheduler jobs.
Connect through streamable HTTP or a local stdio subprocess. Legacy JSON-RPC HTTP
and WebSocket endpoints remain available for existing integrations.

You need a reachable BunkerWeb API and its credentials when authentication is enabled.
See the [BunkerWeb documentation](https://docs.bunkerweb.io) for API setup.

## Quick start

### Connect to an existing BunkerWeb API

1. Clone this repository and open its directory.
2. Copy [.env.example](.env.example) to `.env`. Set `BUNKERWEB_BASE_URL` to an API
   address reachable **from the container**, and supply its bearer token or Basic
   credentials. A container's `localhost` refers to itself.
3. Set `MCP_ALLOWED_HOSTS=localhost,localhost:8080,127.0.0.1,127.0.0.1:8080` for
   local HTTP clients. Keep `SEARCH_MODE=disabled` unless you have a search service.
4. Run `docker compose -f docker-compose-mcp-only.yml up --build -d`.
5. Check liveness with `curl http://127.0.0.1:8080/health`; expect `"status":"healthy"`.
6. Connect your client to `http://127.0.0.1:8080/mcp/`.

The [MCP-only Compose file](docker-compose-mcp-only.yml) loads `.env`, builds the
server, and publishes port 8080. For the published image instead, run
`docker run --rm -p 127.0.0.1:8080:8080 --env-file .env bunkerity/bunkerweb-mcp:latest`.
Use a release tag for a fixed version; the [release workflow](.github/workflows/release.yml)
builds images for AMD64 and ARM64.

### Try the bundled demo stack

Run `docker compose up --build -d` from the repository directory. The default
[docker-compose.yml](docker-compose.yml) starts BunkerWeb 1.6.13, its scheduler and
API, MariaDB, Redis, and this server. It publishes BunkerWeb on ports 80/443 and
MCP on 8080. The included [.mcp.json](.mcp.json) points Claude Code at this server.
The demo publishes `/mcp/` on port 8080 on all interfaces without a client token check.

This file sets the API URL and demo credentials in its service definitions;
editing `.env` does not replace those values. It also disables search and MCP DNS
rebinding protection. Use it on a trusted development machine; review credentials,
port exposure, and host validation before exposing it to a network.

## Connect an MCP client

### Streamable HTTP

Use `/mcp/`, including the trailing slash. The repository's Claude Code config uses:

```json
{
  "mcpServers": {
    "bunkerweb": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp/"
    }
  }
}
```

For a remote server, change the URL to your HTTPS endpoint. When runtime log
access is enabled, add `"headers": {"x-mcp-token": "<shared-secret>"}` inside the
server entry. Read the authentication limits in Security before exposing HTTP.

### Stdio: Claude Code or Claude Desktop

From the repository directory, install with Python 3.11 or newer using the
hash-pinned build and runtime dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes --no-deps -r requirements-build.txt -r requirements.txt
.venv/bin/pip install --no-deps --no-build-isolation .
```

This creates `.venv/bin/bunkerweb-mcp` in your checkout. Use its absolute path in
the client JSON below, replacing `/absolute/path/to` with your repository directory.
It runs a stdio subprocess without an HTTP listener.

For Claude Code, replace the HTTP entry in `.mcp.json` with this configuration.
For Claude Desktop, put it in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bunkerweb": {
      "command": "/absolute/path/to/.venv/bin/bunkerweb-mcp",
      "env": {
        "BUNKERWEB_BASE_URL": "http://api.example.com:8888",
        "BUNKERWEB_API_TOKEN": "<api-token>",
        "SEARCH_MODE": "disabled"
      }
    }
  }
}
```

Replace the executable path and API address with your own. Keep real credentials
out of version control. Stdio uses your local process permissions and API credentials.

## Configuration

[config.py](src/bunkerweb_mcp/config.py) reads environment variables and `.env`.
Defaults below come from that settings model; Compose service values and container
environment variables can override them. `unset` denotes an absent value or an empty string.

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `BUNKERWEB_BASE_URL` | `http://localhost:8888` | Base URL for the BunkerWeb control-plane API. |
| `BUNKERWEB_API_TOKEN` | `unset` | Static API token used for Authorization bearer header (masked in logs). |
| `BUNKERWEB_BASIC_USERNAME` | `unset` | Username for HTTP Basic authentication. |
| `BUNKERWEB_BASIC_PASSWORD` | `unset` | Password for HTTP Basic authentication (masked in logs). |
| `BUNKERWEB_REQUEST_TIMEOUT_SECONDS` | `30.0` | HTTP request timeout in seconds. |
| `BUNKERWEB_MAX_RETRIES` | `3` | Maximum number of retries for transient HTTP errors. |
| `BUNKERWEB_RETRY_BACKOFF_INITIAL` | `0.5` | Initial backoff delay in seconds. |
| `BUNKERWEB_RETRY_BACKOFF_MAX` | `5.0` | Maximum backoff delay in seconds. |
| `BUNKERWEB_WEBSOCKET_TOKEN` | `unset` | Shared secret for legacy RPC/WebSocket access; also required on MCP HTTP when runtime logs are enabled. See Security. |
| `BUNKERWEB_LOG_LEVEL` | `INFO` | Application log level. |
| `BUNKERWEB_LOGS_PATH` | `unset` | Runtime log directory; unset disables log tools. Mount read-only. |
| `BUNKERWEB_PROMPT_CATALOG` | `unset` | Custom tool-prompt JSON path; unset uses the bundled catalog. |
| `BUNKERWEB_REDACT_SECRETS` | `false` | Mask the values of settings whose names match a sensitive pattern in tool and resource outputs, withhold upstream error details and refuse writes to sensitive settings. See Security. |
| `BUNKERWEB_REDACT_PATTERN` | `unset` | Regular expression that replaces the built-in sensitive setting name pattern; unset keeps the built-in one. Avoid nested quantifiers such as `(a+)+$`. |
| `SEARCH_MODE` | `remote` | `remote` enables documentation search; `disabled` omits the tool. Compose and `.env.example` use `disabled`. |
| `SEARCH_API_URL` | `http://localhost:8000` | URL of the remote search service API. |
| `SEARCH_TIMEOUT` | `10.0` | Search API request timeout in seconds. |
| `MCP_ENABLE_DNS_REBINDING_PROTECTION` | `true` | Enable DNS rebinding protection for MCP endpoints (recommended for production). |
| `MCP_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated MCP Host allowlist. Include the port variants clients send. |
| `MCP_ALLOWED_ORIGINS` | `unset` | Comma-separated MCP Origin allowlist for browser clients. |
| `MCP_ENABLE_SKILLS` | `true` | Serve bundled Agent Skills as `skill://bunkerweb/` resources. Set `false` to omit them. |
| `MCP_READ_ONLY` | `false` | Register only read-only tools; write tools are not available on any transport. |
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting on endpoints. |
| `RATE_LIMIT_TOOLS` | `30/minute` | Requests to `/tools` per client IP, when rate limiting is enabled. |
| `RATE_LIMIT_RPC` | `100/minute` | Requests to `/rpc` per client IP, when rate limiting is enabled. |
| `RATE_LIMIT_WS` | `500/minute` | Messages per WebSocket connection, when rate limiting is enabled. |
| `CACHE_ENABLED` | `true` | Cache selected read operations in process memory. |

`WORKERS` is a Docker entrypoint setting, default `1`, rather than a Pydantic
setting. Caches and rate-limit state live in each worker process.

Search needs a separate service: set `SEARCH_MODE=remote` and `SEARCH_API_URL`
to its URL. This repository does not bundle that service. Without it, disable search;
otherwise the server registers `search_bunkerweb_docs` and readiness checks the service.

## Tools and resources

Read `GET /tools` for the running server's tool names, descriptions, and input
schemas. The [registry](src/bunkerweb_mcp/tools/registry.py) defines 44 API tools:

| Group | Tools |
| --- | --- |
| Authentication and probes | `authenticate`, `ping`, `health`, `diagnose` |
| Instances | `list_instances`, `instance_get`, `instance_create`, `instance_update`, `instance_delete`, `instances_delete_bulk`, `instance_ping`, `instances_ping_all`, `instance_stop`, `instances_stop_all`, `reload_instance`, `reload_instances` |
| Bans | `list_bans`, `ban_ip`, `unban_ip` |
| Services | `list_services`, `get_service`, `create_service`, `update_service`, `delete_service`, `convert_service` |
| Global configuration | `global_config_read`, `global_config_update` |
| Custom configuration | `configs_list`, `config_get`, `config_create`, `config_update`, `config_delete`, `configs_delete_bulk`, `configs_upload`, `config_upload_update` |
| Plugins | `plugins_list`, `plugins_upload`, `plugin_delete` |
| Job cache files | `cache_list`, `cache_fetch_file`, `cache_delete_file`, `cache_delete_bulk` |
| Scheduler jobs | `jobs_list`, `jobs_run` |

Optional tools:

- `logs_list`, `logs_read`: register when `BUNKERWEB_LOGS_PATH` points to a runtime
  log directory. Mount it read-only; HTTP mode also requires the shared secret.
  Reads scan up to 1 MiB and return at most 500 lines or 64 KiB of content, with
  cursors for older history. Compressed `.gz` rotations are excluded. Treat log
  content as untrusted data.
- `search_bunkerweb_docs`: registers in remote search mode.

Use `diagnose` to check the connected API's host, reachability, authentication, version,
`MULTISITE`, and instance counts. Pass `service` to inspect its existence, draft state,
and setting-owner counts. An unknown version appears as
`unknown (strictest rules applied)`.

`update_service` checks setting names and ownership before sending changes. It refuses
the request if validation reads fail or `MULTISITE` is not `yes`. It skips invalid or
externally owned keys and unsupported renames; if nothing remains, it sends no write.
After an accepted write, it reads the service back without the result cache. The result
adds `summary` as its first field and a `receipt` with `db` (`verified`, `partial`, or
`unverified`), plus `issues` and `hints` when needed. These report names and reasons,
without setting values. For example, a complete match reads
`DB VERIFIED (2/2 MATCH). LIVE UNVERIFIED.` A failed read-back reads
`WRITE ACCEPTED. DB UNVERIFIED. LIVE UNVERIFIED.` A draft adds `DRAFT: NOT PUBLISHED.`
The summary always ends `LIVE UNVERIFIED.` BunkerWeb 1.6 offers no live-state signal;
the receipt does not prove that instances use the saved configuration.

Tool metadata identifies reads and destructive writes. `MCP_READ_ONLY=true` removes
write tools and their prompts on every transport, including `authenticate`, which
returns a credential. See [ADR 0006](docs/adr/0006-tool-effects-and-read-only-mode.md)
for the version rules and enforcement boundary.

The [MCP adapter](src/bunkerweb_mcp/mcp_adapter.py) also exposes read-only resources:

| URI | Contents |
| --- | --- |
| `config://global` | Global configuration; an empty upstream result includes guidance to use `get_service` with `full=true`. |
| `logs://jobs` | Scheduler jobs and execution history, separate from runtime log files. |
| `bans://active` | Active IP bans. |
| `instances://status` | Registered instances and their status. |
| `skill://bunkerweb/<skill>/<path>` | Bundled Agent Skills and reference files as text; see [Agent Skills](#agent-skills). |

The first four resources return JSON. Skill resources register when `MCP_ENABLE_SKILLS=true`.

Tool guidance comes from the bundled [prompt catalog](src/bunkerweb_mcp/data/tool_prompts.json).
The server exposes matching MCP prompts when catalog text exists. Override the
catalog with `BUNKERWEB_PROMPT_CATALOG`.

Examples and legacy workflow integrations live in [n8n-workflows](n8n-workflows/).

## Agent Skills

The server bundles 13 BunkerWeb Agent Skills (59 files), available through MCP
`resources/list` and `resources/read`. Start with `skill://bunkerweb/bunkerweb/SKILL.md`;
the server's initialization instructions point there too. This entrypoint links
to the other 12 skills on GitHub and to its bundled `references/` files.

Read bundled files at `skill://bunkerweb/<skill>/<path>`, for example
`skill://bunkerweb/bunkerweb/references/docker.md`. Files are served verbatim,
with `text/markdown` for `.md` files. Set `MCP_ENABLE_SKILLS=false` to omit skill
resources and the skills sentence from the server instructions.

Skills come from [bunkerity/bunkerweb-skills](https://github.com/bunkerity/bunkerweb-skills), pinned by [SKILLS_REF](SKILLS_REF).
Refresh with [scripts/sync_skills.py](scripts/sync_skills.py) `--ref <sha>`; CI runs the script with `--check` to detect drift.

## Security

Tools can change configuration, stop instances, delete services, and install plugins.
Grant access only to clients you trust with the configured BunkerWeb API credentials.
Set `MCP_READ_ONLY=true` to serve only read tools on every transport. The server has no
per-client roles.

The HTTP application implements these shared-secret checks:

| Endpoint | Authentication |
| --- | --- |
| `/mcp/` | Requires `x-mcp-token` only when `BUNKERWEB_LOGS_PATH` is configured. Without runtime logs, setting the shared secret alone does not protect MCP HTTP. |
| `/rpc` | Requires `x-mcp-token` when `BUNKERWEB_WEBSOCKET_TOKEN` is non-empty. |
| `/ws` | Requires the `token` query parameter when `BUNKERWEB_WEBSOCKET_TOKEN` is non-empty. |
| `/tools`, `/health`, `/ready`, `/metrics` | No application token check. |

HTTP startup fails if you configure runtime logs without a non-empty shared secret.
`BUNKERWEB_API_TOKEN` and Basic credentials authenticate the server to BunkerWeb;
they do not authenticate MCP clients. The API client prefers a bearer token over Basic auth.

Keep HTTP on a trusted network or behind an authenticated reverse proxy. Use TLS
for remote connections, restrict the exposed endpoints, and configure
`MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` for your clients. DNS rebinding
protection does not replace authentication. See [docs/security.md](docs/security.md).

Set `BUNKERWEB_REDACT_SECRETS=true` to mask the values of sensitive settings (matched by
name) in tool and resource outputs before they reach the client. Upstream API error
details are withheld and only the HTTP status is returned. It is not a content scanner:
custom config snippets, log lines, documentation search results, cache files outside the
denylist and secrets embedded in other values are not masked. See
[docs/security.md](docs/security.md#secret-redaction).

## Observability

The HTTP server exposes Prometheus metrics at `/metrics`, liveness at `/health`,
and dependency readiness at `/ready`. Readiness probes BunkerWeb's `/ping` without
API credentials and, in remote search mode, the search service's `/health`; a
protected API can therefore fail readiness even when authenticated tools work.

See [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) for metrics, tracing, and dashboard
reference. Grafana dashboards: [BunkerWeb MCP](deploy/grafana/dashboards/bunkerweb-mcp.json)
and [MCP BunkerWeb](deploy/grafana/dashboards/mcp-bunkerweb.json).
Tracing is opt-in; this repository does not include a monitoring Compose stack.

## Development

Use the hash-pinned build and development dependencies before installing this
package from source. [AGENTS.md](AGENTS.md) contains installation, lint, formatting,
strict type-checking, and test commands. Tests mock upstream HTTP calls and enforce
an 80% coverage floor.

[.pre-commit-config.yaml](.pre-commit-config.yaml) checks YAML/TOML, file hygiene,
and Python lint/formatting. Run `pre-commit install` to install the local hooks.
The [architecture decisions](docs/adr/README.md) record design context.

## Supply chain

- Build, runtime, and development dependencies use hash-pinned
  `requirements-build.txt`, `requirements.txt`, and `requirements-dev.txt` locks.
  Edit their `.in` sources and regenerate with the uv commands in [AGENTS.md](AGENTS.md);
  do not hand-edit generated locks.
- [CI](.github/workflows/ci.yml) runs quality checks, tests on Python 3.11–3.14,
  CodeQL, and container checks. [Plumber](.github/plumber/README.md) checks CI/CD
  security; [OpenSSF Scorecard](.github/workflows/scorecards-analysis.yml) analyzes
  repository security practices. Badges link to published results.
- The [release workflow](.github/workflows/release.yml) requests build provenance
  and an SBOM for Docker images.
- Follow [.github/SECURITY.md](.github/SECURITY.md) to report vulnerabilities.

## License

MIT. See [LICENSE](LICENSE).
