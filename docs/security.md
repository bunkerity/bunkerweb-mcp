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

## References

- [OWASP: DNS Rebinding](https://owasp.org/www-community/attacks/DNS_Rebinding)
- [MCP Protocol Security](https://spec.modelcontextprotocol.io/specification/2024-11-05/security/)
- [BunkerWeb Documentation](https://docs.bunkerweb.io)
