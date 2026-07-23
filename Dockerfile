# syntax=docker/dockerfile:1.5

# Lightweight MCP server image (no ML dependencies)
# Search is handled by a separate bunkerweb-search-service

FROM python:3.11.15-slim-trixie@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

# Build wheels (no PyTorch or ML dependencies needed)
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels .

# Runtime stage
FROM python:3.11.15-slim-trixie@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python packages from builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && \
    pip uninstall -y setuptools wheel pip && \
    rm -rf /wheels ~/.cache/pip

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
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5).close()"]

CMD ["sh", "-c", "uvicorn bunkerweb_mcp.main:app --host 0.0.0.0 --port 8080 --workers ${WORKERS}"]
