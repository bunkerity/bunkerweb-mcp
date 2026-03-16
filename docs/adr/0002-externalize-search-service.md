# 2. Externalize Search Service for Semantic Documentation

## Context

The MCP server exposes a `search_bunkerweb_docs` tool for semantic search in BunkerWeb documentation. This feature requires:

- An embedding model (sentence-transformers)
- A FAISS index for vector search
- A corpus of ~2600 documentation chunks
- Heavy ML dependencies (torch, transformers, faiss-cpu)

Identified issues:
- **Size**: ML dependencies add ~500MB to the package
- **Performance**: Model loading = ~3-5 seconds at startup
- **Memory**: Memory footprint of ~200-300MB for model + index
- **Deployment**: Increased complexity in constrained environments (Docker, K8s)

The architecture must allow:
1. Embedded mode (all-in-one) for simplicity
2. Remote mode (separate service) for production
3. Flexibility to disable the feature if not needed

## Options Considered

### Option 1: Fully Embedded (Monolithic)

**Description**: Directly integrate semantic search into the main MCP server.

**Advantages**:
- Deployment simplicity (single process)
- No network latency for search queries
- Minimal configuration

**Disadvantages**:
- Docker image size: ~800MB (vs ~300MB without ML)
- Startup time: 3-5 seconds
- Memory consumption: +300MB
- ML dependencies mandatory even if unused
- Difficult scaling (must scale entire MCP)

### Option 2: Separate Service Required

**Description**: Always use a separate search service, no embedded mode.

**Advantages**:
- Lightweight and fast MCP server
- Independent scaling of search service
- ML dependencies isolation

**Disadvantages**:
- Deployment complexity (2 mandatory services)
- Network configuration required
- Added network latency (~5-20ms)
- No simple solution for local dev/test

### Option 3: Hybrid Architecture (Chosen)

**Description**: Externalizable search service with two modes:
- **Local mode**: Search integrated into MCP server (development)
- **Remote mode**: Separate search service (production)

**Advantages**:
- Maximum flexibility according to needs
- Simplified development (local mode)
- Optimized production (remote mode)
- Optional ML dependencies
- Independent scaling in production

**Disadvantages**:
- Slightly increased implementation complexity
- Requires environment configuration
- Two modes to test and maintain

## Decision

**We chose the hybrid architecture (Option 3)** with search service externalization.

### Technical architecture:

```
┌─────────────────────────────────────────────────────┐
│ MCP Server (mcp-bunkerweb)                          │
│  - Tools Registry                                   │
│  - BunkerWeb API Client                             │
│  - Search Client (abstraction)                      │
│    ├─ LocalSearchEngine (mode: local)               │
│    └─ RemoteSearchEngine (mode: remote)             │
└─────────────────────────────────────────────────────┘
                       │
                       │ SEARCH_MODE=remote
                       ▼
┌─────────────────────────────────────────────────────┐
│ Search Service (search-service/)                    │
│  - FastAPI Server                                   │
│  - FAISS Index + Embeddings                         │
│  - Sentence Transformers Model                      │
│  - Endpoint: POST /search                           │
└─────────────────────────────────────────────────────┘
```

### Environment configuration:

```bash
# Local mode (dev/test)
SEARCH_MODE=local

# Remote mode (production)
SEARCH_MODE=remote
SEARCH_API_URL=http://search-service:8001
```

## Consequences

### Positive

- **Lighter MCP Docker image**: 300MB instead of 800MB in remote mode
- **Fast startup**: <1 second instead of 3-5 seconds
- **Flexible scaling**: Search service independently scalable
- **Simplified development**: Local mode for quick tests
- **Optional dependencies**: ML dependencies only if `SEARCH_MODE=local`
- **Isolation**: ML problems don't affect main MCP server

### Negative

- **Production deployment complexity**: Requires 2 services instead of 1
  - **Mitigation**: Docker Compose and Helm charts provided
- **Added latency**: +5-20ms in remote mode
  - **Impact**: Negligible for human interactions
- **Additional configuration**: Environment variables to define
  - **Mitigation**: Sensible defaults (local in dev, remote in prod)

### Neutral

- **Two modes to maintain**: Tests for local and remote necessary
- **Additional network API**: `/search` endpoint from external service

## Notes

### Implementation

The search service is implemented in `search-service/`:

```python
# search-service/main.py
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
import faiss

app = FastAPI()
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
index = faiss.read_index('search_index.faiss')

@app.post("/search")
async def search(query: str, limit: int = 5):
    embedding = model.encode([query])[0]
    distances, indices = index.search([embedding], limit)
    return {"results": [...]}
```

The client in MCP server:

```python
# src/bunkerweb_mcp/search.py
class SearchEngine(Protocol):
    async def search(self, query: str, ...) -> list[SearchResult]: ...

class LocalSearchEngine(SearchEngine):
    # Uses FAISS directly locally

class RemoteSearchEngine(SearchEngine):
    # Calls service via HTTP
```

### Performance metrics

**Local mode**:
- Startup: 3.2s (model loading)
- Query: 50-100ms
- Memory: +280MB

**Remote mode**:
- Startup: 0.8s
- Query: 70-120ms (including network latency)
- Memory: +10MB (HTTP client only)

### Deployment

**Docker Compose** (development):
```yaml
services:
  mcp-server:
    environment:
      SEARCH_MODE: local  # Simple for local dev
```

**Kubernetes** (production):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  env:
    - name: SEARCH_MODE
      value: "remote"
    - name: SEARCH_API_URL
      value: "http://search-service:8001"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: search-service
spec:
  replicas: 2  # Independently scalable
```

### Future evolutions

- **Caching**: Add Redis to cache frequent searches
- **Custom model**: Possibility to fine-tune model on BunkerWeb docs
- **Alternatives**: Possibility to use Elasticsearch/Meilisearch if FAISS insufficient
- **Hybrid mode**: Frequent queries in local cache, rest via remote service

### References

- Code: `src/bunkerweb_mcp/search.py`
- Service: `search-service/`
- Configuration: `src/bunkerweb_mcp/config.py` (SearchMode enum)
- Tests: `tests/test_search.py`
