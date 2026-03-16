"""Prometheus metrics for MCP BunkerWeb server.

This module provides Prometheus metrics for monitoring the MCP server:
- Tool call metrics (count, duration, success/error rate)
- BunkerWeb API metrics
- Cache metrics
- WebSocket connection metrics
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# Server info
mcp_info = Info("mcp_server", "MCP BunkerWeb server information")

# Tool call metrics
tool_calls_total = Counter(
    "mcp_tool_calls_total", "Total number of tool calls", ["tool_name", "status"]
)

tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

# BunkerWeb API metrics
api_requests_total = Counter(
    "bunkerweb_api_requests_total", "Total BunkerWeb API requests", ["endpoint", "method", "status"]
)

api_errors_total = Counter(
    "bunkerweb_api_errors_total", "Total BunkerWeb API errors", ["endpoint", "error_type"]
)

api_duration_seconds = Histogram(
    "bunkerweb_api_duration_seconds",
    "BunkerWeb API request duration in seconds",
    ["endpoint", "method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Connection metrics
active_websockets = Gauge("mcp_active_websockets", "Number of active WebSocket connections")

# Cache metrics
cache_hits_total = Counter("mcp_cache_hits_total", "Total number of cache hits", ["cache_type"])

cache_misses_total = Counter(
    "mcp_cache_misses_total", "Total number of cache misses", ["cache_type"]
)

cache_size_bytes = Gauge("mcp_cache_size_bytes", "Current cache size in bytes", ["cache_type"])

# Resource metrics
resource_calls_total = Counter(
    "mcp_resource_calls_total", "Total number of resource calls", ["resource_uri", "status"]
)

resource_duration_seconds = Histogram(
    "mcp_resource_duration_seconds",
    "Resource call duration in seconds",
    ["resource_uri"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Search metrics (for semantic search)
search_queries_total = Counter(
    "mcp_search_queries_total", "Total number of search queries", ["mode", "status"]
)

search_duration_seconds = Histogram(
    "mcp_search_duration_seconds",
    "Search query duration in seconds",
    ["mode"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

search_results_count = Histogram(
    "mcp_search_results_count",
    "Number of search results returned",
    buckets=(0, 1, 5, 10, 25, 50, 100),
)


def initialize_metrics(version: str = "unknown") -> None:
    """Initialize server information metrics.

    Args:
        version: Server version string
    """
    mcp_info.info({"version": version, "server": "mcp-bunkerweb"})
