# syntax=docker/dockerfile:1.5

# Lightweight MCP server image (no ML dependencies)
# Search is handled by a separate bunkerweb-search-service

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements-build.txt requirements.txt ./
COPY pyproject.toml README.md ./
COPY src ./src

# Build tools come from the hash-pinned lock; only the project itself is built here
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements-build.txt && \
    pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir /wheels .

# Runtime stage
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Fix CVEs
RUN apt-get update && apt-get install -y --no-install-recommends libpcre2-8-0 && rm -rf /var/lib/apt/lists/* # pcre2 10.46-1~deb13u2 -> 10.46-1~deb13u3, still shipped vulnerable by the base image: CVE-2026-103111

# Install Python packages from builder
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt && \
    pip install --no-cache-dir --no-deps /wheels/*.whl && \
    pip check && \
    pip uninstall -y setuptools wheel pip && \
    rm -rf /wheels requirements.txt ~/.cache/pip

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
