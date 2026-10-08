# 5. Optional Secret Redaction at the Tool Registry

Date: 2026-10-08

## Status

Proposed

## Context

Tool handlers serialize BunkerWeb API responses with `model_dump(mode="json")` and return
them unchanged. A `get_service` call on a service using Let's Encrypt DNS challenges returns
`LETS_ENCRYPT_DNS_CREDENTIAL_ITEM` (a DNS provider API token) in clear text, and the same
holds for captcha secrets, Redis passwords, CrowdSec API keys, private keys stored in
`*_KEY_DATA` settings, and private keys or DNS credentials in the job cache. These values
reach the LLM context and every MCP aggregator, proxy or log in between.

`SecretStr` in `config.py` only protects the MCP server's own credentials, in logs. The
BunkerWeb API does not mask `password` settings either: its UI only hides them visually.

Writes are a second concern. If outputs are masked, an agent doing read-modify-write would
send the placeholder back; `PATCH /services/{id}` and `PATCH /global_settings` store values
literally, so the real secret would be overwritten.

## Options Considered

- **Option 1: Redact in each handler**
  - Advantages: Fine-grained control per tool
  - Disadvantages: Around 45 handlers to touch; easy to forget a new tool; the `/rpc`,
    `/ws` and resource paths would each need checking
- **Option 2: Redact in the transport layers (`mcp_adapter`, `/rpc`, `/ws`)**
  - Advantages: Close to the output boundary
  - Disadvantages: Three code paths plus resources; the stdio CLI is a fourth
- **Option 3: Wrap every handler once in `Tools` (registry)**
  - Advantages: Single choke point; `/mcp`, `/rpc`, `/ws`, stdio and MCP resources (which
    call `Tools.get_tool`) all go through the registered handlers; new tools are covered
    automatically
  - Disadvantages: Policy is applied after the in-memory response cache, so cached entries
    stay raw (acceptable: the cache is process memory)

For detecting secrets:

- **Load `type: "password"` settings from `plugins_list` at startup**
  - Advantages: Follows upstream metadata, including external plugins
  - Disadvantages: Startup depends on the API being reachable and the call succeeding; a
    failed load silently disables protection; misses non-password secrets (`*_KEY_DATA`
    are typed `file`, `API_TOKEN` and `DATABASE_URI` are typed `text`)
- **Static name pattern, derived from upstream metadata, overridable by env var**
  - Advantages: Deterministic, works offline and in tests, no extra API call, covers
    multiple-setting suffixes and multisite prefixes with `re.search`
  - Disadvantages: Must be kept in sync with new upstream settings

## Decision

Option 3, with a static pattern. `BUNKERWEB_REDACT_SECRETS` (default `false`) builds a
`RedactionPolicy` (`redaction.py`) that `Tools` uses to wrap every handler:

1. Before the call: refuse `create_service` / `update_service` / `global_config_update`
   when they set a sensitive key; refuse any call whose parameters contain the
   `***REDACTED***` placeholder (base64 uploads are decoded); refuse `cache_fetch_file` on
   sensitive cache files.
2. After the call: mask the values of sensitive keys (only `value`/`default` in the
   `methods=true` shape, empty values kept), the data of sensitive `cache_list` entries,
   and the `authenticate` token.

The default pattern was checked against the 518 settings of BunkerWeb 1.6.15
(`src/common/core/*/plugin.json` and `settings.json`). It matches all 23 settings typed
`password` plus `*_KEY_DATA` private keys, `API_TOKEN` and `DATABASE_URI*`, and nothing
else. `CREDENTIAL_ITEM` is used instead of `CREDENTIAL` so that the
`LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64` flag stays writable. Matching is
case-sensitive: setting names are upper case, while multisite prefixes are lower-case server
names, so a service such as `secret.example.com` would otherwise have every setting masked
and read-only. `BUNKERWEB_REDACT_PATTERN` replaces it for deployments with external plugins and is
compiled at startup so an invalid expression fails fast.

Sensitive cache files are the `letsencrypt`, `customcert`, `selfsigned` and `crowdsec`
plugins, plus `*.key`, `*key.pem` and `instance.id` files from any plugin
(`default-server-cert.key`, `api-server-cert.key`, `client-key.pem`, BunkerNet id).

The API merges `PATCH` payloads with the stored configuration (`services.py` and
`global_settings.py` read the current state, overlay the payload and save the full map), so
refusing sensitive keys does not delete existing secrets.

## Consequences

### Positive

- Secrets in settings and the job cache no longer reach LLM clients when enabled
- One code path covers every transport and resource, current and future tools
- Disabled by default: no behavior change for existing deployments

### Negative

- Agents cannot set secrets; operators manage them in the BunkerWeb UI or API.
  Mitigation: explicit error message naming the offending keys
- The pattern can drift from upstream. Mitigation: tests list every known sensitive
  setting; operators can override the pattern
- `BLACKLIST_HEADER_VALUE` and `GREYLIST_HEADER_VALUE` are masked and read-only because
  upstream types them `password`, although they are filters rather than secrets

### Neutral

- Custom configuration snippets (`config_get`, `configs_list` with `with_data`) are
  free-form text and are not redacted; documented as a known limitation
- Secrets embedded in non-sensitive values (credentials in a URL) are not detected

## Notes

- [Security Guide - Secret Redaction](../security.md#secret-redaction)
- Upstream metadata: `bunkerity/bunkerweb` `src/common/core/*/plugin.json`
- Related ADRs: [0003](0003-pydantic-v2-validation.md) (settings validation)
