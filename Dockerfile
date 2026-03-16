# syntax=docker/dockerfile:1.5

# Lightweight MCP server image (no ML dependencies)
# Search is handled by a separate bunkerweb-search-service

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install git for MCP SDK
RUN apt-get update && \
    apt-get install --no-install-recommends -y git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

# Build wheels (no PyTorch or ML dependencies needed)
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels -r requirements.txt

# Runtime stage
FROM python:3.11-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install curl for health checks
RUN apt-get update && \
    apt-get install --no-install-recommends -y curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages from builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels ~/.cache/pip

# Copy application code
COPY src ./src
COPY prompts ./prompts
COPY .env.example ./.env.example

# Search configuration (optional)
# Set SEARCH_MODE=remote and SEARCH_API_URL to use search service
# Set SEARCH_MODE=disabled to disable search entirely
ENV SEARCH_MODE=remote \
    SEARCH_API_URL=http://localhost:8000 \
    SEARCH_TIMEOUT=10.0

# Performance configuration (can be increased for high-traffic deployments)
ENV WORKERS=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["sh", "-c", "uvicorn bunkerweb_mcp.main:app --host 0.0.0.0 --port 8080 --workers ${WORKERS}"]
