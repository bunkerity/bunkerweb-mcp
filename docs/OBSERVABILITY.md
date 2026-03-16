# Observability Guide

This guide covers the observability stack for the MCP BunkerWeb server, including metrics, tracing, and health checks.

## Table of Contents

- [Overview](#overview)
- [Metrics](#metrics)
- [Distributed Tracing](#distributed-tracing)
- [Health Checks](#health-checks)
- [Monitoring Stack](#monitoring-stack)
- [Grafana Dashboards](#grafana-dashboards)
- [Alerting](#alerting)
- [Troubleshooting](#troubleshooting)

## Overview

The MCP BunkerWeb server implements comprehensive observability through:

- **Prometheus Metrics** - Performance and usage metrics
- **OpenTelemetry Tracing** - Distributed tracing with Jaeger
- **Health Checks** - Liveness and readiness probes
- **Grafana Dashboards** - Pre-built visualization dashboards

## Metrics

### Exposed Metrics

The server exposes Prometheus metrics at `GET /metrics`:

#### Tool Metrics

```promql
# Total tool calls by tool name and status
mcp_tool_calls_total{tool_name="list_services", status="success"}

# Tool execution duration histogram
mcp_tool_duration_seconds_bucket{tool_name="list_services"}
```

#### BunkerWeb API Metrics

```promql
# Total API requests by endpoint, method, and status
bunkerweb_api_requests_total{endpoint="/services", method="GET", status="200"}

# API errors by endpoint and error type
bunkerweb_api_errors_total{endpoint="/services", error_type="timeout"}

# API request duration histogram
bunkerweb_api_duration_seconds_bucket{endpoint="/services", method="GET"}
```

#### Connection Metrics

```promql
# Number of active WebSocket connections
mcp_active_websockets
```

#### Cache Metrics

```promql
# Cache hits by cache type
mcp_cache_hits_total{cache_type="semantic_search"}

# Cache misses by cache type
mcp_cache_misses_total{cache_type="semantic_search"}

# Current cache size in bytes
mcp_cache_size_bytes{cache_type="semantic_search"}
```

#### Resource Metrics

```promql
# Resource calls by URI and status
mcp_resource_calls_total{resource_uri="config://global", status="success"}

# Resource call duration
mcp_resource_duration_seconds_bucket{resource_uri="config://global"}
```

#### Search Metrics

```promql
# Search queries by mode and status
mcp_search_queries_total{mode="remote", status="success"}

# Search duration histogram
mcp_search_duration_seconds_bucket{mode="remote"}

# Number of search results returned
mcp_search_results_count_bucket
```

### Querying Metrics

**Tool Call Rate (requests per second)**
```promql
rate(mcp_tool_calls_total[5m])
```

**Success Rate**
```promql
sum(rate(mcp_tool_calls_total{status="success"}[5m])) /
sum(rate(mcp_tool_calls_total[5m])) * 100
```

**P95 Latency**
```promql
histogram_quantile(0.95, rate(mcp_tool_duration_seconds_bucket[5m]))
```

**Cache Hit Rate**
```promql
sum(rate(mcp_cache_hits_total[5m])) /
(sum(rate(mcp_cache_hits_total[5m])) + sum(rate(mcp_cache_misses_total[5m]))) * 100
```

## Distributed Tracing

### Configuration

Tracing is configured via environment variables:

```bash
# Enable/disable tracing (default: true)
OTEL_TRACING_ENABLED=true

# OTLP endpoint for trace export (default: http://jaeger:4317)
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Enable console exporter for debugging (default: false)
OTEL_USE_CONSOLE_EXPORTER=false
```

### Auto-Instrumentation

The server automatically instruments:

- **FastAPI endpoints** - HTTP request spans
- **httpx client** - Outgoing HTTP request spans

### Custom Spans

To add custom spans in your code:

```python
from bunkerweb_mcp.tracing import get_tracer

tracer = get_tracer(__name__)

async def my_function():
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("custom_attribute", "value")
        # Your code here
        span.set_attribute("result_count", 42)
```

### Viewing Traces

1. Access Jaeger UI at http://localhost:16686
2. Select service: `mcp-bunkerweb`
3. Search for traces by operation, tags, or duration

## Health Checks

### Liveness Probe

**Endpoint:** `GET /health`

Checks if the server process is running.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00.000Z"
}
```

**Kubernetes Configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3
```

### Readiness Probe

**Endpoint:** `GET /ready`

Checks if the server can handle requests (all dependencies available).

**Response (200 OK):**
```json
{
  "status": "ready",
  "checks": {
    "bunkerweb_api": true,
    "search_service": true
  },
  "timestamp": "2025-01-15T10:30:00.000Z"
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "not_ready",
  "checks": {
    "bunkerweb_api": false,
    "search_service": true
  },
  "timestamp": "2025-01-15T10:30:00.000Z"
}
```

**Kubernetes Configuration:**
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 2
```

## Monitoring Stack

### Starting the Monitoring Stack

```bash
# Start Prometheus, Grafana, and Jaeger
docker-compose -f docker-compose.monitoring.yml up -d

# View logs
docker-compose -f docker-compose.monitoring.yml logs -f
```

### Service Endpoints

- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/admin)
- **Jaeger UI:** http://localhost:16686

### Architecture

```
┌─────────────┐
│ MCP Server  │ :8080
│  /metrics   │────┐
└─────────────┘    │
                   │ scrape
┌─────────────┐    │
│ MCP Server  │────┤
│  (OTLP)     │────┼────────> ┌────────────┐
└─────────────┘    │          │ Prometheus │ :9090
                   │          └──────┬─────┘
                   │                 │
                   └─────────────────┤
                                     │ datasource
                              ┌──────▼─────┐
                              │  Grafana   │ :3000
                              └────────────┘

┌─────────────┐
│ MCP Server  │
│  (traces)   │──────────────> ┌────────────┐
└─────────────┘   OTLP gRPC    │   Jaeger   │ :16686
                  :4317         └────────────┘
```

## Grafana Dashboards

### MCP BunkerWeb Dashboard

Pre-configured dashboard located at: `deploy/grafana/dashboards/mcp-bunkerweb.json`

**Panels:**

1. **Tool Calls Rate** - Requests per second by tool and status
2. **Tool Success Rate** - Percentage of successful tool calls (gauge)
3. **Active WebSockets** - Current number of WebSocket connections
4. **Tool Latency (P50/P95/P99)** - Latency percentiles over time
5. **BunkerWeb API Errors** - Error rate by endpoint and error type
6. **Cache Hit Rate** - Percentage of cache hits (gauge)
7. **BunkerWeb API Latency (P95)** - API request latency by endpoint
8. **Search Results Count (P95)** - Distribution of search result counts

### Accessing Dashboards

1. Navigate to http://localhost:3000
2. Login with `admin/admin`
3. Go to Dashboards → Browse
4. Select "MCP BunkerWeb Dashboard"

### Creating Custom Dashboards

Grafana supports custom dashboard creation. Use the Prometheus datasource and the metrics listed above.

## Alerting

### Alert Rules

Alert rules are defined in `deploy/prometheus/alerts.yml`.

**Available Alerts:**

- **HighToolErrorRate** - More than 10% of tool calls failing
- **HighToolLatency** - P95 latency exceeds 5 seconds
- **BunkerWebAPIErrors** - API errors detected
- **NoActiveWebSockets** - No active connections for 30 minutes
- **LowCacheHitRate** - Cache hit rate below 30%
- **MCPServerDown** - Server unreachable
- **BunkerWebAPIUnreachable** - All API requests failing

### Configuring Alertmanager (Optional)

To enable alerting to external systems (Slack, PagerDuty, email):

1. Deploy Alertmanager:
```yaml
alertmanager:
  image: prom/alertmanager:v0.26.0
  ports:
    - "9093:9093"
  volumes:
    - ./deploy/alertmanager/config.yml:/etc/alertmanager/config.yml
```

2. Update `deploy/prometheus/prometheus.yml`:
```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

3. Create `deploy/alertmanager/config.yml` with notification receivers

## Troubleshooting

### Metrics Not Appearing

1. Check that the `/metrics` endpoint is accessible:
   ```bash
   curl http://localhost:8080/metrics
   ```

2. Verify Prometheus is scraping the target:
   - Go to http://localhost:9090/targets
   - Check that `mcp-bunkerweb` target is UP

3. Check Prometheus logs:
   ```bash
   docker-compose -f docker-compose.monitoring.yml logs prometheus
   ```

### Traces Not Showing in Jaeger

1. Verify tracing is enabled:
   ```bash
   echo $OTEL_TRACING_ENABLED  # should be "true"
   ```

2. Check Jaeger is receiving traces:
   - Go to http://localhost:16686
   - Check for service `mcp-bunkerweb`

3. Verify OTLP endpoint is correct:
   ```bash
   echo $OTEL_EXPORTER_OTLP_ENDPOINT  # should be http://jaeger:4317
   ```

4. Enable console exporter for debugging:
   ```bash
   export OTEL_USE_CONSOLE_EXPORTER=true
   ```

### High Memory Usage

If Prometheus or Grafana consume too much memory:

1. Reduce Prometheus retention:
   ```yaml
   command:
     - '--storage.tsdb.retention.time=7d'  # Default is 15d
   ```

2. Limit Grafana plugins:
   ```yaml
   environment:
     - GF_INSTALL_PLUGINS=  # Empty = no extra plugins
   ```

### Dashboard Not Loading

1. Verify dashboard provisioning:
   ```bash
   docker exec mcp-grafana ls /var/lib/grafana/dashboards
   ```

2. Check Grafana logs:
   ```bash
   docker-compose -f docker-compose.monitoring.yml logs grafana
   ```

3. Manually import dashboard:
   - Go to Dashboards → Import
   - Upload `deploy/grafana/dashboards/mcp-bunkerweb.json`

## Best Practices

### Production Deployment

1. **Enable persistence** - Use named volumes for Prometheus and Grafana data
2. **Configure retention** - Set appropriate data retention policies
3. **Secure endpoints** - Add authentication to Prometheus and Grafana
4. **Set up alerting** - Configure Alertmanager with appropriate receivers
5. **Monitor the monitors** - Set up external health checks for monitoring stack

### Performance Optimization

1. **Reduce cardinality** - Avoid high-cardinality labels (IPs, UUIDs, etc.)
2. **Sample traces** - For high-traffic systems, sample traces at 10-50%
3. **Aggregate metrics** - Use recording rules for frequently queried metrics
4. **Limit scrape interval** - Increase scrape interval for low-change metrics

### Security

1. **Restrict access** - Use firewall rules to limit access to monitoring ports
2. **Use TLS** - Enable HTTPS for Grafana and Prometheus in production
3. **Rotate credentials** - Change default Grafana password immediately
4. **Audit access** - Enable audit logging in Grafana

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
