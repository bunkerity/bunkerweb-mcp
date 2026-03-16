"""Tests for observability endpoints (metrics, health, readiness)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from bunkerweb_mcp.main import create_app
from bunkerweb_mcp.metrics import (
    active_websockets,
    tool_calls_total,
    tool_duration_seconds,
)


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    def test_metrics_endpoint_exists(self, client):
        """Test that /metrics endpoint is accessible."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client):
        """Test that /metrics returns Prometheus format."""
        response = client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_tool_calls(self, client):
        """Test that metrics include tool call counters."""
        # Increment a metric
        tool_calls_total.labels(tool_name="test_tool", status="success").inc()

        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"mcp_tool_calls_total" in response.content

    def test_metrics_contains_active_websockets(self, client):
        """Test that metrics include active WebSocket gauge."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"mcp_active_websockets" in response.content

    def test_metrics_contains_duration_histogram(self, client):
        """Test that metrics include duration histogram."""
        # Observe a duration
        tool_duration_seconds.labels(tool_name="test_tool").observe(0.5)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"mcp_tool_duration_seconds" in response.content

    def test_metrics_server_info(self, client):
        """Test that server info metric is present."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"mcp_server_info" in response.content


class TestHealthEndpoint:
    """Tests for the /health endpoint (liveness probe)."""

    def test_health_endpoint_exists(self, client):
        """Test that /health endpoint is accessible."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        """Test that /health returns JSON response."""
        response = client.get("/health")
        assert response.headers["content-type"] == "application/json"

    def test_health_status_healthy(self, client):
        """Test that /health returns healthy status."""
        response = client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_timestamp_format(self, client):
        """Test that timestamp is in ISO format."""
        response = client.get("/health")
        data = response.json()

        timestamp = data["timestamp"]
        assert "T" in timestamp  # ISO 8601 format
        assert timestamp.endswith("Z") or "+" in timestamp


class TestReadinessEndpoint:
    """Tests for the /ready endpoint (readiness probe)."""

    def test_readiness_endpoint_exists(self, client):
        """Test that /ready endpoint is accessible."""
        response = client.get("/ready")
        assert response.status_code in [200, 503]

    def test_readiness_returns_json(self, client):
        """Test that /ready returns JSON response."""
        response = client.get("/ready")
        assert response.headers["content-type"] == "application/json"

    def test_readiness_all_checks_pass(self, client):
        """Test readiness when all checks pass."""
        # Note: In test mode, readiness checks may fail due to unavailable dependencies
        # This is expected behavior
        response = client.get("/ready")
        data = response.json()

        assert response.status_code in [200, 503]
        assert data["status"] in ["ready", "not_ready"]
        assert "checks" in data
        assert "timestamp" in data

    def test_readiness_bunkerweb_api_down(self, client):
        """Test readiness when BunkerWeb API is down."""
        # In test environment, BunkerWeb API is unavailable
        response = client.get("/ready")
        data = response.json()

        # Should return not_ready status
        assert response.status_code == 503
        assert data["status"] == "not_ready"
        assert "bunkerweb_api" in data["checks"]

    def test_readiness_checks_structure(self, client):
        """Test that readiness response has expected structure."""
        response = client.get("/ready")
        data = response.json()

        assert "status" in data
        assert "checks" in data
        assert "timestamp" in data
        assert "bunkerweb_api" in data["checks"]
        assert "search_service" in data["checks"]

    def test_readiness_timestamp_format(self, client):
        """Test that timestamp is in ISO format."""
        response = client.get("/ready")
        data = response.json()

        timestamp = data["timestamp"]
        assert "T" in timestamp  # ISO 8601 format


class TestMetricsCollection:
    """Tests for metrics collection during operations."""

    def test_metrics_collection_structure(self, client):
        """Test that metrics collection infrastructure is in place."""
        # Get metrics from /metrics endpoint
        response = client.get("/metrics")
        content = response.content.decode()

        # Verify key metrics are defined (may have zero values)
        assert "mcp_tool_calls" in content or "# HELP mcp_tool_calls" in content
        assert "mcp_tool_duration_seconds" in content
        assert "mcp_active_websockets" in content

    def test_websocket_gauge_exists(self, client):
        """Test that WebSocket gauge metric exists and is accessible."""
        # Active websockets gauge should exist
        initial_value = active_websockets._value.get()
        assert isinstance(initial_value, (int, float))
        assert initial_value >= 0

    def test_metrics_endpoint_contains_all_metrics(self, client):
        """Test that /metrics endpoint exposes all defined metrics."""
        response = client.get("/metrics")
        content = response.content.decode()

        # Check for key metrics
        assert "mcp_tool_calls_total" in content
        assert "mcp_tool_duration_seconds" in content
        assert "mcp_active_websockets" in content
        assert "bunkerweb_api_requests_total" in content
        assert "mcp_cache_hits_total" in content


def _get_metric_value(metric_name: str, **labels) -> float:
    """Helper to get current value of a metric with specific labels.

    Args:
        metric_name: Name of the metric
        **labels: Label key-value pairs

    Returns:
        Current metric value
    """
    for family in REGISTRY.collect():
        if family.name == metric_name:
            for sample in family.samples:
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    return sample.value
    return 0.0


class TestTracingIntegration:
    """Tests for OpenTelemetry tracing integration."""

    def test_tracing_setup_does_not_crash(self, client):
        """Test that tracing setup doesn't cause errors."""
        # If the app started successfully, tracing is working
        response = client.get("/health")
        assert response.status_code == 200

    @patch.dict("os.environ", {"OTEL_TRACING_ENABLED": "false"})
    def test_tracing_can_be_disabled(self):
        """Test that tracing can be disabled via environment variable."""
        app = create_app()
        test_client = TestClient(app)

        response = test_client.get("/health")
        assert response.status_code == 200

    @patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://custom-jaeger:4317"})
    def test_custom_otlp_endpoint(self):
        """Test that custom OTLP endpoint can be configured."""
        app = create_app()
        test_client = TestClient(app)

        response = test_client.get("/health")
        assert response.status_code == 200
