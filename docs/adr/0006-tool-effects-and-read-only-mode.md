# 6. Tool Effects and Read-Only Mode

Date: 2026-10-20

## Status

Proposed

## Context

BunkerWeb 1.6 can accept a service PATCH without changing the requested settings.
The API skips settings that it cannot overwrite because another method owns them.
Older releases also skip unknown names. With `MULTISITE=no`, per-service settings
do not apply. An API success response alone cannot confirm the database contents.

Ownership and rename rules differ within 1.6:

| Version | Existing explicit setting owners the API may replace |
| --- | --- |
| v1.6.5 or unknown | `api` only |
| v1.6.6-v1.6.13 | `api`, `ui` |
| v1.6.14+ | `api`, `ui`, `wizard` |

Default or inherited settings remain writable. A request for the value already
stored does not require replacing its owner. Renames require v1.6.15 or later;
older releases can lose the service's custom configs and job cache during a rename.
For v1.6.15+, the API enforces service ownership for renames.

BunkerWeb 1.6 exposes no configuration revision or live-state signal. A reload with
`test=true` tests the configuration and then reloads; it is not a dry run. Operators
also need a way to expose read tools without granting access to mutations.

## Options Considered

- **Keep success responses and describe writes as applied.** This needs no new
  checks but hides skipped settings and overstates the evidence.
- **Classify and restrict tools in each transport.** This allows local rules but
  duplicates policy across HTTP MCP, stdio, `/rpc`, `/ws`, and `/tools`.
- **Share effects and filtering in `Tools`, then verify service writes.** This
  keeps policy in one place and distinguishes database evidence from live state,
  at the cost of extra upstream reads.

## Decision

Use the shared registry and database read-back.

`TOOL_EFFECTS` in `tools/registry.py` classifies tools as reads or writes and marks
destructive writes. Deletion, stopping, overwriting, weakening protection, and
reloads count as destructive. `authenticate` counts as a write because it returns
a credential. `diagnose` and `search_bunkerweb_docs` count as reads.

The table drives MCP `readOnlyHint` and write `destructiveHint` annotations, and
the `read_only` and `destructive` fields in tool descriptors. We do not advertise
idempotency: the client retries transient errors, including mutation failures.

`MCP_READ_ONLY` defaults to `false`. When true, `Tools` removes writes before any
transport registers them. Discovery and execution then use the same read allowlist.
The adapter also omits prompts for removed tools. This covers HTTP MCP, stdio,
`/rpc`, `/ws`, and `/tools`.

Before `update_service`, the handler reads global settings and the service without
the result cache. For requested variables, it validates names against the plugin
setting catalogue. It refuses the whole request when a required validation read
fails or has an unexpected shape, when the service does not exist, or when
`MULTISITE` is not `yes`.

The handler skips individual keys with invalid names, service prefixes, or
incompatible ownership. `SERVER_NAME` belongs in the `server_name` parameter.
It skips renames on versions below v1.6.15 or unknown versions. It sends the
remaining fields; if none remain, it refuses the request without a PATCH.
Version discovery uses the API's OpenAPI version. Unknown versions use v1.6.5
ownership rules and disable renames.

After an accepted PATCH, the handler reads back the service without the result
cache. The result adds `summary` first and a `receipt` with `db`, plus `issues`
and `hints` when needed. Existing response keys follow. The database outcomes are:

| `db` | Example summary |
| --- | --- |
| `verified` | `DB VERIFIED (2/2 MATCH). LIVE UNVERIFIED.` |
| `partial` | `DB PARTIAL (2/3 MATCH, 1 SKIPPED). LIVE UNVERIFIED.` |
| `unverified` | `WRITE ACCEPTED. DB UNVERIFIED. LIVE UNVERIFIED.` |

Counts include skipped requested fields, `server_name`, and `is_draft`. Only a
read-back that confirms a draft adds `DRAFT: NOT PUBLISHED.` before
`LIVE UNVERIFIED.` and a draft issue, without changing the database outcome.
Issues and hints contain setting names and reasons, without setting values. A
failed read-back returns the unverified receipt without the draft marker and does
not trigger another PATCH.
The summary always ends `LIVE UNVERIFIED.`

`diagnose` reports the API host and port without credentials, reachability,
authentication, version, `MULTISITE`, and instance counts. With `service`, it adds
existence, draft state, and explicit setting-owner counts. Unknown versions appear
as `unknown (strictest rules applied)`. It cannot check live configuration.

## Consequences

### Positive

- Clients can distinguish read tools from writes and destructive actions.
- Operators can expose only reads through the shared registry.
- Agents can report database matches, skips, and failed verification without
  claiming a configuration is live.

### Negative

- Service updates need more reads and can fail validation during an upstream outage.
- Unknown versions restrict ownership changes and disable renames until version
  discovery succeeds.
- A database match still requires separate checks of live traffic and instances.

### Neutral

- `/rpc` falls back to the SDK tool manager only for tools the adapter registered.
  Future tools outside `Tools` must preserve this read-only boundary.
- Discovered versions and setting catalogues are cached for 600 seconds per upstream
  base URL. Unknown versions are cached for 30 seconds before discovery is retried.
  Plugin uploads and deletions invalidate the catalogue, including uncertain outcomes.
- Receipts cover `update_service`. Other writes retain their own response formats.
- Read-only mode is server-wide. It does not provide per-client roles or replace
  client authentication.

## Notes

- [README: Tools and resources](../../README.md#tools-and-resources)
- [Secret redaction](0005-secret-redaction.md)
- [Security guide](../security.md)
