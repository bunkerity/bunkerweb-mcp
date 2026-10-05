# syntax=docker/dockerfile:1.5

# Lightweight MCP server image (no ML dependencies)
# Search is handled by a separate bunkerweb-search-service

FROM python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151 AS builder

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
FROM python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151 AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Fix CVEs
RUN apt-get update && apt-get install -y --no-install-recommends libpcre2-8-0 && rm -rf /var/lib/apt/lists/* # pcre2 10.46-1~deb13u2 -> 10.46-1~deb13u3, still shipped vulnerable by the base image: CVE-2026-103111

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
