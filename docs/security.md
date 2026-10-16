# Security Configuration Guide

## DNS Rebinding Protection

The MCP server includes built-in protection against DNS rebinding attacks. This security feature validates incoming request headers to ensure they come from trusted sources.

### What is DNS Rebinding?

DNS rebinding is an attack where:
1. An attacker controls a malicious domain (e.g., `evil.com`)
2. The DNS is configured to first resolve to a public IP, then switch to your internal IP
3. A victim's browser visits the malicious domain
4. The attacker's JavaScript makes requests to your internal MCP server, bypassing Same-Origin Policy

### How Protection Works

The server validates the HTTP `Host` header against a whitelist of allowed hosts. Requests from unauthorized hosts receive a `421 Misdirected Request` error with the message "Invalid Host header".

## Configuration

Configure DNS rebinding protection via environment variables in your `.env` file:

### Enable/Disable Protection

```bash
# Recommended: Keep enabled in production
MCP_ENABLE_DNS_REBINDING_PROTECTION=true

# Only disable for testing/debugging
# MCP_ENABLE_DNS_REBINDING_PROTECTION=false
```

### Allowed Hosts

**CRITICAL**: You must include **both** the hostname alone AND with the port number.

```bash
# Comma-separated list of allowed Host header values
MCP_ALLOWED_HOSTS=yourdomain.com,yourdomain.com:443,internal.local,internal.local:8080
```

**Why both variants?**
- Browsers and HTTP clients send different `Host` headers depending on the port
- Standard ports (80, 443): Usually sent without port → `Host: example.com`
- Non-standard ports: Sent with port → `Host: example.com:8085`

### Allowed Origins (CORS)

Only needed if browser-based clients will access the server:

```bash
# For browser-based MCP clients
MCP_ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

## Environment-Specific Examples

### Development (Local Machine)

```bash
MCP_ENABLE_DNS_REBINDING_PROTECTION=true
MCP_ALLOWED_HOSTS=localhost,localhost:8080,127.0.0.1,127.0.0.1:8080
MCP_ALLOWED_ORIGINS=
```

### Staging/Internal Network

```bash
MCP_ENABLE_DNS_REBINDING_PROTECTION=true
# Include internal hostname, internal IP, and any port variants
MCP_ALLOWED_HOSTS=staging.internal,staging.internal:8085,192.168.1.100,192.168.1.100:8085
MCP_ALLOWED_ORIGINS=
```

### Production (Docker/Kubernetes)

```bash
MCP_ENABLE_DNS_REBINDING_PROTECTION=true
# Public domain, internal service names, and localhost for health checks
MCP_ALLOWED_HOSTS=mcp.yourdomain.com,mcp.yourdomain.com:443,mcp-bunkerweb,mcp-bunkerweb:8080,localhost,127.0.0.1
MCP_ALLOWED_ORIGINS=https://yourdomain.com
```

### Production (Behind Reverse Proxy)

When behind nginx/Traefik/BunkerWeb:

```bash
MCP_ENABLE_DNS_REBINDING_PROTECTION=true
# Include the public domain AND any internal routing names
MCP_ALLOWED_HOSTS=mcp.example.com,mcp.example.com:443,mcp-service,mcp-service:8080
MCP_ALLOWED_ORIGINS=
```

**Important**: If your reverse proxy rewrites the `Host` header, configure it to preserve the original:
- Nginx: `proxy_set_header Host $host;`
- Traefik: Automatically preserves Host header
- BunkerWeb: Configure `REVERSE_PROXY_HOST` appropriately

## Testing Your Configuration

### 1. Valid Request (Should Succeed)

```bash
curl -X POST http://yourdomain.com:8085/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: `200 OK` with list of tools

### 2. Invalid Host (Should Fail)

```bash
curl -X POST http://untrusted.com:8085/mcp/ \
  -H "Host: untrusted.com:8085" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: `421 Misdirected Request` with message "Invalid Host header"

### 3. Check Server Logs

The MCP server logs all security validations. Look for:

```json
{"level": "WARNING", "message": "Rejected request with invalid Host header: untrusted.com"}
```

## Troubleshooting

### Error: "Invalid Host header"

**Symptoms**: Client receives `421 Misdirected Request`

**Causes**:
1. Host not in `MCP_ALLOWED_HOSTS`
2. Forgot to include port number variant
3. Reverse proxy is rewriting `Host` header

**Solutions**:
1. Add the host to `MCP_ALLOWED_HOSTS`
2. Include both `hostname` and `hostname:port`
3. Configure reverse proxy to preserve `Host` header
4. Check actual `Host` header sent: `curl -v http://yourserver/mcp/`

### Claude Code Cannot Connect

**Symptoms**: Claude Code fails to connect to MCP server

**Solutions**:
1. Check `.mcp.json` URL matches an allowed host
2. If using `http://192.168.1.100:8085/mcp`, add `192.168.1.100:8085` to allowed hosts
3. Try using hostname instead of IP: `http://apps:8085/mcp`
4. Verify server is accessible: `curl http://yourserver:8085/tools`

### Docker Networking Issues

**Symptoms**: Works with `localhost` but not with container name

**Solutions**:
1. Add Docker service name to `MCP_ALLOWED_HOSTS`: `mcp-bunkerweb,mcp-bunkerweb:8080`
2. Add Docker bridge network IPs if needed
3. Use Docker hostname resolver: `mcp-bunkerweb` instead of IP

## Security Best Practices

### Production Checklist

- ✅ Keep `MCP_ENABLE_DNS_REBINDING_PROTECTION=true`
- ✅ Only list hosts you control in `MCP_ALLOWED_HOSTS`
- ✅ Use HTTPS in production (configure reverse proxy)
- ✅ Set `BUNKERWEB_API_TOKEN` for API authentication
- ✅ Set `BUNKERWEB_WEBSOCKET_TOKEN` when enabling `BUNKERWEB_LOGS_PATH`
- ✅ Mount BunkerWeb logs read-only and treat their contents as untrusted input
- ✅ Set `BUNKERWEB_REDACT_SECRETS=true` when an LLM client or MCP aggregator uses the server
- ✅ Use firewall rules to restrict access to MCP port
- ✅ Regularly audit `MCP_ALLOWED_HOSTS` list
- ✅ Monitor logs for rejected requests (potential attacks)

### When to Disable Protection

**NEVER disable in production** unless you have alternative protections (e.g., firewall rules, VPN-only access).

Only disable for:
- Local development testing
- Troubleshooting connectivity issues (temporarily)
- Internal networks with strict physical security

Even then, prefer adding hosts to the allowlist rather than disabling protection.

## Advanced Configuration

### Dynamic Host Lists

For complex deployments, generate `MCP_ALLOWED_HOSTS` dynamically:

```bash
# In Dockerfile or startup script
export MCP_ALLOWED_HOSTS="$(hostname),$(hostname):8080,localhost,127.0.0.1"
```

### Kubernetes Deployment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-config
data:
  MCP_ALLOWED_HOSTS: "mcp.example.com,mcp.example.com:443,mcp-bunkerweb,mcp-bunkerweb.default.svc.cluster.local,mcp-bunkerweb.default.svc.cluster.local:8080"
```

### Environment-Based Configuration

```bash
# .env.production
MCP_ALLOWED_HOSTS=prod.example.com,prod.example.com:443

# .env.staging
MCP_ALLOWED_HOSTS=staging.example.com,staging.example.com:8085,192.168.1.100,192.168.1.100:8085
```

## Secret Redaction

Tool results are returned as the BunkerWeb API serializes them. Reading a service or the
global configuration therefore exposes secrets in clear text (DNS provider credentials in
`LETS_ENCRYPT_DNS_CREDENTIAL_ITEM`, captcha secrets, Redis passwords, private keys...), and
they end up in the LLM context and in every MCP aggregator, proxy or log in between.
`SecretStr` only masks the server's own credentials, and only in logs.

Enable redaction when an LLM client or an aggregator sits in front of the server:

```bash
BUNKERWEB_REDACT_SECRETS=true
```

The option is off by default. When enabled, it applies to every tool call and resource read
that goes through the tool registry, whatever the transport (`/mcp`, `/rpc`, `/ws`, stdio).

The guarantee is narrow: values are masked **by setting name**, in tool results and
resources, and upstream error bodies are withheld. It is not a content scanner. Anything the
masking cannot recognise by name is returned as is; see [Known limitations](#known-limitations)
for the exceptions.

### Masked outputs

The value of every key matching the sensitive pattern is replaced by `***REDACTED***`.
Empty values are left untouched, so an agent can still tell whether a secret is configured.
With `methods=true`, only `value` and `default` are masked and the metadata stays visible:

```json
"LETS_ENCRYPT_DNS_CREDENTIAL_ITEM": {
  "value": "***REDACTED***", "global": false, "method": "ui", "default": "", "template": null
}
```

Keys suffixed for multiple settings (`AUTH_BASIC_PASSWORD_1`) and prefixed by a server name
in the multisite global view (`www.example.com_REDIS_PASSWORD`) are matched too. The Biscuit
token returned by the `authenticate` tool is masked as well.

### Upstream errors

An error body returned by the BunkerWeb API can echo submitted or stored values, so with
redaction enabled a failed API call reaches the client with the HTTP status only:

```text
BunkerWeb API error (HTTP 422); details withheld because BUNKERWEB_REDACT_SECRETS is enabled
```

Any other unexpected failure is reported as `Unexpected tool execution error`. Errors the
server raises itself keep their message: a refused write, and a rejected path segment (see
[Path segments](#path-segments)).

### Path segments

Identifiers that the server places in a BunkerWeb API URL path are validated before the
request is sent: service, hostname, plugin id, job name, cache file name, and custom config
type and name. A value is rejected when it is empty, equals `.` or `..`, or contains `/`,
`\`, `%` or a control character:

```text
Invalid service: path separators, percent signs, control characters and '.'/'..' are not allowed
```

Accepted values are percent-encoded. The check runs whether or not redaction is enabled. It
stops a caller from steering a request to another API route, for example to a cache file that
the redaction policy refuses to return.

For the cache, the policy checks the file name BunkerWeb will actually look up. BunkerWeb
turns a `folder:` token into a path by dropping the prefix and replacing every `_` with `/`,
so `folder:a_b.key` is checked as `a/b.key`. Local log sources read by `logs_list` and
`logs_read` are not API paths and are not affected.

### Refused writes

The following calls fail with a validation error before anything is sent to the API:

- `create_service`, `update_service` or `global_config_update` setting a sensitive key;
- any tool call whose parameters contain `***REDACTED***`, including decoded
  `content_base64` uploads. The API would otherwise store the placeholder literally,
  overwriting the real secret.

Manage secrets through the BunkerWeb UI or API directly. Updates are merged by the API, so
leaving a sensitive key out of an `update_service` or `global_config_update` call keeps its
stored value.

### Job cache

`cache_fetch_file` is refused, and `cache_list` masks the `data` of matching entries, for:

- the `letsencrypt` (certbot keys, ACME accounts, DNS credentials), `customcert`,
  `selfsigned` and `crowdsec` (bouncer API key) plugins;
- file names ending in `.key` or `key.pem`, and BunkerNet's `instance.id`.

### Sensitive pattern

The built-in pattern is matched with `re.search` against setting names:

```text
PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|LICENSE_KEY|PRIVATE_KEY|_KEY_DATA|CREDENTIAL_ITEM|HEADER_VALUE|DATABASE_URI
```

It covers every setting typed `password` in the BunkerWeb 1.6 core plugins, the private keys
(`CUSTOM_SSL_KEY_DATA`, `GRPC_SSL_KEY_DATA`, `REVERSE_PROXY_SSL_KEY_DATA`), `API_TOKEN` and
`DATABASE_URI` (which may embed a password). Look-alike flags such as
`LETS_ENCRYPT_DNS_CREDENTIAL_DECODE_BASE64` or `CORS_ALLOW_CREDENTIALS` are not matched and
remain writable.

`BUNKERWEB_REDACT_PATTERN` **replaces** the built-in pattern. To extend it, copy the pattern
above and append your own alternatives, for example `...|DATABASE_URI|MY_PLUGIN_SECRET`.
Matching is case-sensitive; prefix with `(?i)` to change that. An invalid expression makes
the server fail at startup.

### Known limitations

- Custom configuration snippets (`config_get`, and `configs_list` with `with_data=true`) are
  free-form nginx or ModSecurity text and are **not** redacted. Do not store secrets in them.
- Log lines returned by `logs_read` are free text and are **not** redacted. A line can contain
  a token, a password in a query string or any value a request carried. Leave `BUNKERWEB_LOGS_PATH`
  unset when clients must not see such content.
- Documentation search (`search_bunkerweb_docs`) is registered outside the tool registry and
  is outside the redaction boundary. It returns public documentation from a separate service,
  so no secret is expected in its results, and the placeholder check on tool parameters does
  not apply to it. If the service returns a malformed result, the
  resulting validation error is logged by the server without redaction.
- Cache files are protected by a denylist: the `letsencrypt`, `customcert`, `selfsigned` and
  `crowdsec` plugins, and file names ending in `.key`, `key.pem` or equal to `instance.id`.
  A plugin not on the list can store a secret under an ordinary file name, and that file is
  returned as is.
- Detection relies on setting names. A secret held by an external plugin setting that does
  not match the pattern, or embedded in a non-sensitive value (credentials inside a URL), is
  returned as is. Extend `BUNKERWEB_REDACT_PATTERN` for such plugins.
- `BUNKERWEB_REDACT_PATTERN` is compiled with Python's `re` and run with `re.search` against
  every key of every result. A pattern with nested quantifiers, such as `(a+)+$`, backtracks
  catastrophically on a crafted key and stalls the server. Keep custom patterns simple.
- The in-memory response cache keeps raw API responses; redaction applies on each read.

## References

- [OWASP: DNS Rebinding](https://owasp.org/www-community/attacks/DNS_Rebinding)
- [MCP Protocol Security](https://spec.modelcontextprotocol.io/specification/2024-11-05/security/)
- [BunkerWeb Documentation](https://docs.bunkerweb.io)
