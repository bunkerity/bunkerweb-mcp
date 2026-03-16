"""OpenTelemetry tracing configuration for MCP BunkerWeb server.

This module configures distributed tracing using OpenTelemetry:
- Auto-instrumentation for FastAPI endpoints
- Auto-instrumentation for httpx HTTP client
- Custom spans for tool execution
- OTLP export to Jaeger or other backends
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

if TYPE_CHECKING:
    from fastapi import FastAPI

LOGGER = logging.getLogger(__name__)


def setup_tracing(app: FastAPI, service_name: str = "mcp-bunkerweb") -> None:
    """Configure OpenTelemetry tracing for the application.

    Args:
        app: FastAPI application instance
        service_name: Service name for traces (default: "mcp-bunkerweb")
    """
    # Get OTLP endpoint from environment (default to Jaeger)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    use_console_exporter = os.getenv("OTEL_USE_CONSOLE_EXPORTER", "false").lower() == "true"
    tracing_enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() == "true"

    if not tracing_enabled:
        LOGGER.info("OpenTelemetry tracing is disabled")
        return

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)
        LOGGER.info(f"OpenTelemetry OTLP exporter configured: {otlp_endpoint}")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning(f"Failed to configure OTLP exporter: {e}")

    # Optionally add console exporter for debugging
    if use_console_exporter:
        console_exporter = ConsoleSpanExporter()
        console_processor = BatchSpanProcessor(console_exporter)
        provider.add_span_processor(console_processor)
        LOGGER.info("OpenTelemetry console exporter enabled")

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    LOGGER.info("FastAPI auto-instrumentation enabled")

    # Auto-instrument httpx client
    HTTPXClientInstrumentor().instrument()
    LOGGER.info("httpx auto-instrumentation enabled")


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for creating custom spans.

    Args:
        name: Tracer name (typically __name__ of the module)

    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)
