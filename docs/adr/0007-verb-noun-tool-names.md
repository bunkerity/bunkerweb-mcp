# 7. One verb_noun Scheme for Tool Names

Date: 2026-11-03

## Status

Accepted

## Context

Glama grades this server with the Tool Definition Quality Score (TDQS) and shows the grade on the
README badge. The v0.6.0 rescan (2026-10-23) gave **A 3.6**, up from C 2.9. The remaining points
were in the coherence dimensions and in the weakest tools:

| Part | Glama v0.6.0 |
| --- | --- |
| Mean tool score (45 tools) | about 4.3 |
| Weakest tool (`authenticate`) | 3.1 |
| Disambiguation | 4 |
| Naming consistency | 2 |
| Tool count | 2 |

The TDQS rubric (tdqs 0.1.0, server coherence prompt) scores naming 5 for a "consistent
verb_noun pattern throughout (e.g. list_issues, create_issue, delete_issue)". Glama gave this
server a 2 because the names mixed `list_services` and `get_service` with `instance_get`,
`instances_ping_all`, `config_get`, `configs_list`, `cache_delete_file` and `jobs_run`.

The rubric scores tool count 5 for 3 to 15 tools, 3 for 16 to 25 and 2 for 26 or more. Reaching
25 tools would need multi-mode tools that cost more per-tool points than they gain, so this
decision does not try. It removes only true duplicates.

Several tools were also pairs of the same operation: one for a single object, one for a list
(`instance_delete` and `instances_delete_bulk`), and probes that returned the same static answer
(`ping` and `health`).

## Options Considered

- **Keep the names and rewrite the descriptions only**
  - Advantages: no break for clients.
  - Disadvantages: the naming score stays at 2; the duplicate pairs stay.
- **Rename to `verb_noun` and keep the old names as aliases**
  - Advantages: no immediate break for clients.
  - Disadvantages: every alias is one more tool in `tools/list`, so the tool count and the
    naming score get worse; aliases on five transports are code nobody tests well.
- **Rename to `verb_noun`, fold the duplicates, register no aliases**
  - Advantages: one scheme, 45 scored tools become 37, descriptions stop explaining which of two
    similar tools to pick.
  - Disadvantages: breaks every client that calls a tool by name.

## Decision

Rename every tool to `verb_noun` with no aliases, and fold the duplicates. The noun is plural
when the tool lists or acts on several objects and singular when it acts on exactly one. An old
name is never registered on any transport (stdio, `/mcp/`, `/tools`, `/rpc`, `/ws`); calling one
returns the unknown-tool error.

Merges:

- `ping_api` replaces `ping` and `health`. BunkerWeb's `/ping` and `/health` both return a static
  OK and both skip authentication, so one call covers both.
- `ping_instances` takes an optional `hostname`. With it, one instance is pinged; without it,
  every instance. A read, so pinging all on omission is safe.
- `stop_instances` and `reload_instances` take `hostname` or `all=true`, exactly one of them.
  Anything else is a validation error that names both parameters, and no upstream call is made.
  Leaving a parameter out can never stop or reload every instance. `reload_instances` keeps its
  `test` flag on both paths.
- `delete_instances`, `delete_configs` and `delete_cache_files` take a list of at least one item
  and always call the bulk endpoint, whatever the list length. The bulk routes report the items
  they could not delete (for instances, `skipped`), so the single-object client methods lose
  their only caller and are deleted.
- `convert_service` folds into `update_service` with `is_draft`. Both the PATCH route and the
  convert route set `{service}_IS_DRAFT` and end in `_persist_config`, so the end state is the
  same.

**Draft toggle.** An `is_draft`-only `update_service` call keeps `preflight_update` and the
receipt. The preflight refuses unless `MULTISITE=yes`. `convert_service` had no such gate, but its
route writes the same prefixed `{service}_IS_DRAFT` key, which the single-site saver skips, so
convert in single-site mode already reported success without changing anything. Drafts are a
per-service, multisite concept, and the receipt proves the stored `IS_DRAFT`. A missing service
now gives the preflight's validation error instead of convert's 400.

**Reused name, new contract.** `reload_instances` keeps its name but now needs `hostname` or
`all=true`. A call with only `test` fails validation.

The `authenticate` tool becomes `create_api_token`. Its description no longer promises an expiry
the API does not return: `POST /auth` returns only the token, and its lifetime is the BunkerWeb
setting `API_BISCUIT_TTL_SECONDS`.

### Rename table

Tools served by default: 36 registry tools plus `search_bunkerweb_docs` (37 scored). Log tools
register only when `BUNKERWEB_LOGS_PATH` is set.

| Old name | New name |
| --- | --- |
| `authenticate` | `create_api_token` |
| `ping`, `health` | `ping_api` |
| `diagnose` | `diagnose_bunkerweb` |
| `instance_get` | `get_instance` |
| `instance_create` | `create_instance` |
| `instance_update` | `update_instance` |
| `instance_delete`, `instances_delete_bulk` | `delete_instances` |
| `instance_ping`, `instances_ping_all` | `ping_instances` |
| `instance_stop`, `instances_stop_all` | `stop_instances` (`hostname` or `all=true`) |
| `reload_instance`, `reload_instances` | `reload_instances` (`hostname` or `all=true`) |
| `ban_ip` | `ban_ips` |
| `unban_ip` | `unban_ips` |
| `convert_service` | `update_service` with `is_draft` |
| `global_config_read` | `get_global_config` |
| `global_config_update` | `update_global_config` |
| `configs_list` | `list_configs` |
| `config_get` | `get_config` |
| `config_create` | `create_config` |
| `configs_upload` | `create_configs_from_files` |
| `config_update` | `update_config` |
| `config_upload_update` | `update_config_from_file` |
| `config_delete`, `configs_delete_bulk` | `delete_configs` |
| `plugins_list` | `list_plugins` |
| `plugins_upload` | `install_plugins` |
| `plugin_delete` | `uninstall_plugin` |
| `cache_list` | `list_cache_files` |
| `cache_fetch_file` | `get_cache_file` |
| `cache_delete_file`, `cache_delete_bulk` | `delete_cache_files` |
| `jobs_list` | `list_jobs` |
| `jobs_run` | `run_jobs` |
| `logs_list` | `list_logs` |
| `logs_read` | `read_log` |

Unchanged: `list_instances`, `list_bans`, `list_services`, `get_service`, `create_service`,
`update_service`, `delete_service`, `search_bunkerweb_docs`.

## Consequences

### Positive

- Naming: one scheme, so a client can guess the name of a tool it has not seen.
- Disambiguation: no single-versus-bulk pairs and no three-way probe cluster to read around.
- Safety: stopping or reloading every instance needs an explicit `all=true`.
- Less code: the dead handlers, parameter models and client methods are deleted with their tests.

### Negative

- Breaking change for every client that calls a tool by name, and for saved prompts and
  workflows. Mitigation: ship it as its own release with the rename table in the release notes;
  the repo's n8n workflows and docs move in the same change.
- No aliases, so an old name fails at once instead of degrading. Mitigation: the unknown-tool
  error names the tool; the table above maps every old name.
- The Prometheus `tool_name` label (`mcp_tool_calls_total`, `mcp_tool_duration_seconds`) takes the
  new values, so historical series split at the upgrade. The Grafana dashboards use
  `{{tool_name}}` and keep working; alert rules that match an old name need an update.
- A delete of one item now goes through the bulk endpoint and returns the bulk result shape.

### Neutral

- Tool count stays above 25, so the tool-count score stays at 2. This is accepted.
- Resource URIs (`config://global`, `bans://active`, ...) and the HTTP endpoints (`/health`,
  `/ready`, `/tools`, `/rpc`, `/ws`, `/metrics`) do not change.
- Glama rescans only on a GitHub release, so the badge moves after the tag.

## Notes

- Scoring method and results: [docs/tdqs.md](../tdqs.md).
- Related: [ADR 0005](0005-secret-redaction.md) and
  [ADR 0006](0006-tool-effects-and-read-only-mode.md), whose tool-name maps follow the renames.
