# BunkerWeb MCP Server (Python)

A production-ready MCP server that exposes BunkerWeb's internal API to large language models via a constrained tool interface. The server provides both HTTP (for testing) and WebSocket (for MCP clients) JSON-RPC endpoints, strict input validation, and a resilient async client with retries.

## Quick Start with Claude Code

```bash
# Install the package
git clone https://github.com/bunkerity/bunkerweb-mcp.git
cd bunkerweb-mcp

# For demo/testing you dont need to change anything
# Configure environment
cp .env.example .env
# Edit .env to set BUNKERWEB_BASE_URL

# Launch BunkerWeb Stack
docker compose up -d

# If you launch Claude in this repo, it will automatically read the .mcp.json file with mcp server url.
# You can then just launch Claude
claude
> List all BunkerWeb instances
> List my BunkerWeb services
> Review @config://global for security improvements

# If youu want to connect to a remote BunkerWeb mcp serveur 
# We recommand to use BunkerWeb itself to protect the MCP service, and use SSL: 
claude mcp add --transport http bunkerweb http://remote-ip:8080/mcp/

claude mcp add --transport http bunkerweb https://your-domain.com/mcp/
```

## Features
- **37 comprehensive tools** covering all BunkerWeb operations (instances, services, configs, bans, plugins, jobs, cache)
- **🔍 AI-powered semantic search in BunkerWeb Documentation** via remote search service (optional, configurable)
- **MCP resources** for read-only data access (global config, job logs, active bans, instance status)
- **Multiple transports**: Stdio (for Claude Code), HTTP, WebSocket
- **Official MCP SDK integration** with FastMCP for compliant clients (Claude Code, VS Code, Claude Desktop)
- **Robust async client** with retry/backoff and typed Pydantic models
- **Prompt catalog** providing contextual guidance for each tool
- **FastAPI app** exposing `/rpc` HTTP and `/ws` WebSocket JSON-RPC endpoints (legacy)
- **CLI entry point** (`bunkerweb-mcp`) for easy integration
- **Comprehensive documentation** including CLAUDE.md with BunkerWeb expertise
- **Optional authentication** via shared-secret token or API bearer token
- **Structured JSON logging** with metrics for observability
- **Unit tests** with mocked HTTP transport
- **Docker and Kubernetes** deployment manifests
- **⚡ Performance optimizations** (Sprint 2):
  - **Caching layer** with configurable TTLs for read-only operations
  - **Optional rate limiting** to protect against request floods
  - **Multi-worker support** for high-traffic deployments
  - **Load testing suite** with Locust for performance validation

## Requirements
- Access to a BunkerWeb API (default `http://localhost:8888`)

## Installation

### From Source
```bash
# Clone the repository
git clone https://github.com/bunkerity/bunkerweb-mcp.git
cd bunkerweb-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Or install from requirements
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### From PyPI (when published)
```bash
pip install bunkerweb-mcp
```

The requirements file pulls the MCP SDK directly from GitHub; ensure `git` is installed on the host before installing dependencies.
Update `.env` with your API base URL and either a token or basic credentials if required.

### Development Context

The repository includes a `CLAUDE.md` file that provides Claude Code with comprehensive BunkerWeb expertise and best practices. This file is automatically loaded when working in this repository with Claude Code, giving the assistant context about:
- BunkerWeb architecture and components
- Security module configuration (ModSecurity, Antibot, etc.)
- Common operational workflows
- Troubleshooting guidelines
- Best practices for production deployments

## Configuration
All settings are configurable via environment variables (see `.env.example`):

| Variable | Description | Default |
| --- | --- | --- |
| `BUNKERWEB_BASE_URL` | Base URL to the BunkerWeb API | `http://localhost:8888` |
| `BUNKERWEB_API_TOKEN` | Optional static bearer token | empty |
| `BUNKERWEB_BASIC_USERNAME` | Optional username for HTTP Basic auth | empty |
| `BUNKERWEB_BASIC_PASSWORD` | Optional password for HTTP Basic auth | empty |
| `BUNKERWEB_REQUEST_TIMEOUT_SECONDS` | HTTP timeout in seconds | `30` |
| `BUNKERWEB_MAX_RETRIES` | Retry attempts for transient failures | `3` |
| `BUNKERWEB_RETRY_BACKOFF_INITIAL` | Initial backoff delay (seconds) | `0.5` |
| `BUNKERWEB_RETRY_BACKOFF_MAX` | Maximum backoff delay (seconds) | `5.0` |
| `BUNKERWEB_WEBSOCKET_TOKEN` | Shared-secret required by `/ws` and `/rpc` | empty |
| `BUNKERWEB_LOG_LEVEL` | Logging level | `INFO` |
| `BUNKERWEB_PROMPT_CATALOG` | Optional JSON file with per-tool prompts | built-in catalog |
| `RATE_LIMIT_ENABLED` | Enable rate limiting (Sprint 2) | `false` |
| `RATE_LIMIT_TOOLS` | Rate limit for /tools endpoint | `30/minute` |
| `RATE_LIMIT_RPC` | Rate limit for /rpc endpoint | `100/minute` |
| `RATE_LIMIT_WS` | Rate limit for WebSocket messages | `500/minute` |
| `CACHE_ENABLED` | Enable caching layer (Sprint 2) | `true` |
| `WORKERS` | Number of Uvicorn workers (Docker only) | `1` |

## Running the server

### HTTP mode (recommended)

#### docker-compose
```bash
docker compose up --build
```
The compose file maps `host.docker.internal` so the container can reach a locally running BunkerWeb API on port `8888`.

#### Local (uvicorn)
```bash
uvicorn bunkerweb_mcp.main:app --host 0.0.0.0 --port 8080
```

#### Docker
```bash
docker build -t bunkerweb-mcp .
docker run --rm -p 8080:8080 --env-file .env bunkerweb-mcp
```

#### Kubernetes

Deploy to Kubernetes with BunkerWeb ingress controller integration:

```bash
# Quick deployment
kubectl apply -f deploy/kubernetes/namespace.yaml
kubectl apply -f deploy/kubernetes/secret.yaml      # Edit credentials first
kubectl apply -f deploy/kubernetes/configmap.yaml
kubectl apply -f deploy/kubernetes/deployment.yaml
kubectl apply -f deploy/kubernetes/service.yaml

# Optional: External access via BunkerWeb ingress
kubectl apply -f deploy/kubernetes/ingress.yaml

# Optional: Autoscaling and monitoring
kubectl apply -f deploy/kubernetes/hpa.yaml
kubectl apply -f deploy/kubernetes/servicemonitor.yaml

# Verify deployment
kubectl get pods -n bunkerweb
kubectl logs -n bunkerweb -l app=mcp-bunkerweb --tail=100 -f
```

**Key features**:
- BunkerWeb ingress controller with ModSecurity WAF and Antibot protection
- Horizontal Pod Autoscaler (2-10 replicas based on CPU/memory)
- Prometheus metrics and OpenTelemetry tracing
- Health checks with `/health` and `/ready` endpoints
- Configurable via ConfigMap and Secrets

For detailed deployment instructions, troubleshooting, and configuration options, see [deploy/kubernetes/README.md](deploy/kubernetes/README.md).

### Stdio mode (recommended for local use)

If you installed the package locally (`pip install -e .`), Claude Code and VS Code can launch the server as a subprocess via stdio, without Docker.

Configuration examples for Claude Code, VS Code, and Claude Desktop are in the dedicated section: **MCP integration > Stdio Transport**.

> **Important**: use the **absolute path** to the virtualenv binary in `command` (get it with `which bunkerweb-mcp`). Relative commands can fail because MCP clients do not inherit your shell PATH.

## MCP integration

The server supports multiple transport protocols for MCP clients:

### Stdio Transport (Recommended for Claude Code and VS Code)

#### Claude Code — `.mcp.json`

```json
{
  "mcpServers": {
    "bunkerweb": {
      "type": "stdio",
      "command": "/path/to/your/.venv/bin/bunkerweb-mcp",
      "env": {
        "BUNKERWEB_BASE_URL": "http://<bunkerweb-api-host>:8888",
        "BUNKERWEB_API_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

#### VS Code — `.mcp.json`

VS Code uses `servers` (not `mcpServers`):

```json
{
  "servers": {
    "bunkerweb": {
      "type": "stdio",
      "command": "/path/to/your/.venv/bin/bunkerweb-mcp",
      "env": {
        "BUNKERWEB_BASE_URL": "http://<bunkerweb-api-host>:8888",
        "BUNKERWEB_API_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

Adapt `command` to your actual virtualenv path (`which bunkerweb-mcp` after activating it) and set `BUNKERWEB_BASE_URL` to your BunkerWeb API address.

For **Claude Desktop**, add the same block to your `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, Linux: `~/.config/Claude/claude_desktop_config.json`) — the `type` field can be omitted as Desktop defaults to stdio:

```json
{
  "mcpServers": {
    "bunkerweb": {
      "command": "/path/to/your/.venv/bin/bunkerweb-mcp",
      "env": {
        "BUNKERWEB_BASE_URL": "http://<bunkerweb-api-host>:8888",
        "BUNKERWEB_API_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

Verify the server is detected by Claude Code:
```bash
claude mcp list
# bunkerweb: /path/to/your/.venv/bin/bunkerweb-mcp (stdio)
```

**Note**: The stdio transport runs the server as a subprocess communicating via stdin/stdout — no port, no Docker required.

### HTTP Transport (For Remote Servers)

Point MCP-compatible clients at the streamable HTTP endpoint:

- **Transport**: Streamable HTTP
- **URL**: `http://localhost:8080/mcp`

Configure in `.mcp.json`:
```json
{
  "mcpServers": {
    "bunkerweb": {
      "url": "http://localhost:8080/mcp",
      "transport": "http"
    }
  }
}
```

### Legacy Transports

Legacy JSON-RPC transports remain available for existing workflows:
- **HTTP**: `/rpc` endpoint
- **WebSocket**: `/ws` endpoint

Use the `BUNKERWEB_WEBSOCKET_TOKEN` value when a client requires authentication; the same secret protects all transports.

## MCP Resources

The server exposes read-only resources that can be referenced in Claude Code conversations using the `@` syntax:

| URI | Description |
| --- | --- |
| `@config://global` | Current global BunkerWeb configuration |
| `@logs://jobs` | Scheduler job execution history |
| `@bans://active` | Currently active IP bans |
| `@instances://status` | Health status of all instances |

Example usage in Claude Code:
```
> Review @config://global and suggest security hardening improvements
> Check @bans://active for any suspicious patterns
```

## Semantic Search

The MCP server uses an AI-powered semantic search tool for BunkerWeb documentation via a remote search service.

**⚠️ IMPORTANT**: The search functionality has been externalized to a separate service for better scalability and reduced image size. 
**It is not yet available to the public** 

### Configuration

Add to your `.env` file:

```bash
# Enable or disable search
SEARCH_MODE=disabled          # 'remote' or 'disabled'

# Search service URL
SEARCH_API_URL=https://search.example.com

# Request timeout
SEARCH_TIMEOUT=10.0
```

### Using with Docker Compose

The included `docker-compose.yml` runs both services:

```bash
# Start both MCP and search service
docker-compose up -d

# Check search service health
curl http://localhost:8000/health

# MCP server will automatically use search service
```

### Disable Search

To run the MCP server without search:

```bash
# In .env
SEARCH_MODE=disabled

# In docker-compose.yml, comment out search-service
```

## Tool catalogue
Query the `/tools` endpoint for JSON descriptors. Available tools include:

**Documentation & Search:**
- `search_bunkerweb_docs`: Semantic search across BunkerWeb documentation (`query`, `limit`, `category`)

**Instance Management:**
- `ping`: Check API reachability
- `health`: Read the API health probe
- `list_instances`: List registered BunkerWeb instances
- `reload_instances`: Reload configuration across all instances (`test` flag supported)
- `reload_instance`: Reload a specific instance (`hostname`, optional `test`)

**Security & Bans:**
- `list_bans`: Retrieve active bans
- `ban_ip`: Ban one or multiple IPs (`bans` array with `ip`, `exp`, `reason`, `service`)
- `unban_ip`: Remove bans (`bans` array with `ip`, optional `service`)

**Services:**
- `list_services`: List services (`with_drafts` flag)
- `get_service`: Fetch details for a specific service (`service`, `full`, `methods`, `with_drafts`)
- `delete_service`: Delete a service (`service`)

And 27 more tools covering configs, plugins, jobs, and cache management.

Each descriptor now carries a `prompt` field sourced from the prompt catalog. MCP clients can surface these short instructions to keep assistant answers consistent across tools.

## Prompt catalog
The server ships with `prompts/tool_prompts.json`, a curated set of guidance strings keyed by tool name. At startup the catalog is loaded once and injected into tool descriptors as well as every RPC/WebSocket response. Override the location with `BUNKERWEB_PROMPT_CATALOG` if you need custom wording.

## JSON-RPC usage
### HTTP example
```bash
curl -X POST http://localhost:8080/rpc \
  -H "Content-Type: application/json" \
  -H "X-MCP-Token: $BUNKERWEB_WEBSOCKET_TOKEN" \
  -d '{"id":"1","tool":"list_instances","params":{}}
```

### WebSocket example (websocat)
```bash
echo '{"id":"ping-1","tool":"ping","params":{}}' \
  | websocat -H "Sec-WebSocket-Protocol: json" ws://localhost:8080/ws?token=$BUNKERWEB_WEBSOCKET_TOKEN
```

## Tests
```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout
```
src/bunkerweb_mcp/
├─ main.py                # FastAPI app + JSON-RPC endpoints
├─ cli.py                 # CLI entry point for stdio mode
├─ mcp_adapter.py         # MCP server integration
├─ client.py              # Resilient async client for BunkerWeb
├─ tools.py               # MCP tools with strict validation
├─ config.py              # Environment-driven settings
├─ prompt_catalog.py      # Prompt loading helpers
├─ exceptions.py          # Domain-specific exceptions
├─ search_client.py       # Lightweight HTTP client for search service
├─ schemas/               # Pydantic models for requests/responses
└─ utils/logging.py       # Structured logging helpers

prompts/
└─ tool_prompts.json      # Default tool prompts exposed to MCP clients
```

## Observability

The MCP server includes comprehensive observability features:

### Prometheus Metrics

Metrics are exposed at `GET /metrics` in Prometheus format:

```bash
curl http://localhost:8080/metrics
```

**Available metrics:**
- `mcp_tool_calls_total{tool_name, status}` - Total tool calls by status
- `mcp_tool_duration_seconds` - Tool execution duration histogram
- `mcp_active_websockets` - Active WebSocket connections
- `bunkerweb_api_requests_total{endpoint, method, status}` - BunkerWeb API requests
- `bunkerweb_api_errors_total{endpoint, error_type}` - API errors
- `mcp_cache_hits_total{cache_type}` - Cache hits
- `mcp_cache_misses_total{cache_type}` - Cache misses
- `mcp_search_queries_total{mode, status}` - Search queries

### OpenTelemetry Tracing

Distributed tracing with automatic instrumentation:

```bash
# Configure tracing via environment variables
OTEL_TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
```

Traces are automatically generated for:
- HTTP requests (FastAPI)
- Outgoing API calls (httpx)
- Tool executions

View traces in Jaeger UI at http://localhost:16686

### Health Checks

**Liveness probe** - Checks if the server is running:
```bash
curl http://localhost:8080/health
# Response: {"status": "healthy", "timestamp": "..."}
```

**Readiness probe** - Checks if the server can handle requests:
```bash
curl http://localhost:8080/ready
# Response: {"status": "ready", "checks": {"bunkerweb_api": true, "search_service": true}, "timestamp": "..."}
```

Kubernetes configuration:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Monitoring Stack

Start the full observability stack (Prometheus, Grafana, Jaeger):

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

**Access:**
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Jaeger UI**: http://localhost:16686

### Grafana Dashboard

Pre-built dashboard with 8 panels:
1. Tool Calls Rate
2. Tool Success Rate
3. Active WebSockets
4. Tool Latency (P50/P95/P99)
5. BunkerWeb API Errors
6. Cache Hit Rate
7. BunkerWeb API Latency
8. Search Results Count

Import from `deploy/grafana/dashboards/mcp-bunkerweb.json`

### Alerting

Pre-configured Prometheus alerts in `deploy/prometheus/alerts.yml`:
- High tool error rate (>10%)
- High latency (P95 > 5s)
- BunkerWeb API errors
- Low cache hit rate (<30%)
- Service health issues

### Structured Logging

Logs are emitted as single-line JSON for ingestion by log processors. Each `tool_call` log carries a `metrics` object with the tool name and `duration_seconds` for latency tracking. Adjust `BUNKERWEB_LOG_LEVEL` as needed.

**See [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) for the complete observability guide.**

## Performance Tuning

The MCP server includes several performance optimizations introduced in Sprint 2:

### Caching Layer

**Enabled by default** - Caches read-only API operations to reduce latency and load on BunkerWeb API.

```bash
# Configure in .env
CACHE_ENABLED=true  # Default: true
```

**Cache TTLs** (configured in `src/bunkerweb_mcp/cache.py`):
- `list_services`: 300s (5 minutes)
- `global_config`: 600s (10 minutes)
- `list_instances`: 60s (1 minute)
- `list_bans`: 30s (30 seconds)

Cache is automatically invalidated on write operations (create, update, delete).

### Rate Limiting

**Disabled by default** - Optional protection against request floods.

```bash
# Enable in .env for production
RATE_LIMIT_ENABLED=true  # Default: false
RATE_LIMIT_TOOLS=30/minute
RATE_LIMIT_RPC=100/minute
RATE_LIMIT_WS=500/minute
```

When enabled, exceeding rate limits returns HTTP 429 or WebSocket error.

### Multi-Worker Deployment

For high-traffic deployments, increase Uvicorn workers:

```bash
# Docker environment variable
WORKERS=4  # Default: 1

# Local development
uvicorn bunkerweb_mcp.main:app --workers 4
```

**Kubernetes resource allocation:**
```yaml
resources:
  requests:
    cpu: "100m"      # Baseline for single worker
    memory: "256Mi"
  limits:
    cpu: "500m"      # Increase for multiple workers
    memory: "512Mi"
```

**Recommendation**: Set `WORKERS` to CPU count × 2 for production deployments.

### Load Testing

Verify performance with the included Locust test suite:

```bash
# Install locust
pip install -r requirements-dev.txt

# Run load test
./scripts/load-test.sh

# Or customize parameters
HOST=http://localhost:8080 USERS=200 RUN_TIME=10m ./scripts/load-test.sh
```

**Performance targets** (Sprint 2):
- **Throughput**: > 1000 req/s sustained
- **P95 latency**: < 100ms
- **Error rate**: 0% at 100 concurrent users

Reports are generated in `./load-test-reports/`.

### Performance Tips

1. **Enable caching** (`CACHE_ENABLED=true`) for read-heavy workloads
2. **Disable rate limiting** by default (set `RATE_LIMIT_ENABLED=false`) unless under attack
3. **Use multiple workers** (`WORKERS=4`) only for high traffic (>100 req/s)
4. **Monitor cache hit rate** via logs to tune TTLs
5. **Increase resources** in Kubernetes based on load test results

## Security notes

### DNS Rebinding Protection (Important!)

The MCP server includes built-in DNS rebinding protection. You **must** configure allowed hosts:

```bash
# In your .env file - REQUIRED for production
MCP_ENABLE_DNS_REBINDING_PROTECTION=true
MCP_ALLOWED_HOSTS=yourdomain.com,yourdomain.com:443,internal-host,internal-host:8085
```

**Critical**: Include **both** hostname alone and with port (e.g., `apps,apps:8085`).

See [docs/security.md](docs/security.md) for detailed configuration guide.

### Other Security Best Practices

- Populate `BUNKERWEB_API_TOKEN` when the target API requires authentication.
- When using HTTP Basic auth, set `BUNKERWEB_BASIC_USERNAME` and `BUNKERWEB_BASIC_PASSWORD` via secrets management.
- Set `BUNKERWEB_WEBSOCKET_TOKEN` to require a shared secret for both `/rpc` and `/ws`.
- Ensure the MCP server runs on a trusted network; the API can modify BunkerWeb state.
- Use HTTPS via reverse proxy (nginx, Traefik, or BunkerWeb) in production.

## Documentation

### Project Documentation

- **[Architecture Decision Records (ADR)](docs/adr/README.md)** - Major architectural decisions with context and rationale
- **[Sprint 3: Maintenability](docs/SPRINT_3_MAINTENABILITY.md)** - Code quality and documentation improvements
- **[Observability Guide](docs/OBSERVABILITY.md)** - Complete guide to metrics, tracing, and monitoring (Sprint 4)
- **[Migration Guide](MIGRATION.md)** - Guide for upgrading from v1.x to v2.x
- **[Security Guide](docs/security.md)** - DNS rebinding protection and security best practices
- **[Claude Development Guide](CLAUDE.md)** - BunkerWeb expertise for Claude Code

### API Documentation

All tool handlers include comprehensive Google-style docstrings with:
- Detailed functionality description
- Parameter specifications with types and defaults
- Return value format documentation
- Exception handling guidance
- Usage examples

Example: [src/bunkerweb_mcp/tools.py](src/bunkerweb_mcp/tools.py) contains 40+ fully documented handlers.

### Architecture Decisions

Key architectural choices are documented in ADRs:
- [ADR-0001: FastMCP SDK](docs/adr/0001-use-fastmcp-sdk.md) - MCP protocol implementation
- [ADR-0002: Externalize Search](docs/adr/0002-externalize-search-service.md) - Search service architecture
- [ADR-0003: Pydantic V2](docs/adr/0003-pydantic-v2-validation.md) - Data validation framework
- [ADR-0004: Async HTTPX](docs/adr/0004-async-httpx-client.md) - HTTP client choice

### Contributing

See individual ADRs for architectural guidance when proposing changes. All new tool handlers must include:
- Complete Google-style docstrings
- Unit tests with >80% coverage
- Updates to relevant ADRs if architectural changes are involved

## License
MIT
