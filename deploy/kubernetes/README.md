# Kubernetes Deployment Guide

This directory contains Kubernetes manifests for deploying the MCP BunkerWeb server.

## Prerequisites

- Kubernetes cluster (1.24+)
- `kubectl` configured to access your cluster
- BunkerWeb Ingress Controller (for Ingress)
- Prometheus Operator (optional, for ServiceMonitor)
- Metrics Server (optional, for HorizontalPodAutoscaler)

## Quick Start

### 1. Create Namespace

```bash
kubectl apply -f namespace.yaml
```

### 2. Configure Secrets

```bash
# Copy and edit the secret file
cp secret.yaml secret.local.yaml

# Edit with your actual credentials
vim secret.local.yaml

# Apply the secret
kubectl apply -f secret.local.yaml

# IMPORTANT: Do not commit secret.local.yaml to git
```

### 3. Configure Settings

Edit [configmap.yaml](configmap.yaml) to match your environment:

```yaml
data:
  BUNKERWEB_BASE_URL: "https://your-bunkerweb-api.example.com"
  MCP_ALLOWED_HOSTS: "mcp-bunkerweb.example.com,your-custom-hosts"
```

Apply the ConfigMap:

```bash
kubectl apply -f configmap.yaml
```

### 4. Deploy the Application

```bash
# Deploy all core components
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Optional: Deploy Ingress (adjust host in ingress.yaml first)
kubectl apply -f ingress.yaml

# Optional: Enable autoscaling
kubectl apply -f hpa.yaml

# Optional: Enable Prometheus monitoring
kubectl apply -f servicemonitor.yaml
```

### 5. Verify Deployment

```bash
# Check pod status
kubectl get pods -n bunkerweb

# Check service
kubectl get svc -n bunkerweb

# Check logs
kubectl logs -n bunkerweb -l app=mcp-bunkerweb --tail=100 -f

# Test health endpoints
kubectl port-forward -n bunkerweb svc/mcp-bunkerweb 8080:8080
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

## Manifest Overview

| File | Description | Required |
|------|-------------|----------|
| [namespace.yaml](namespace.yaml) | Namespace definition | ✅ Yes |
| [configmap.yaml](configmap.yaml) | Non-sensitive configuration | ✅ Yes |
| [secret.yaml](secret.yaml) | API tokens and credentials (example) | ✅ Yes |
| [deployment.yaml](deployment.yaml) | Main application deployment | ✅ Yes |
| [service.yaml](service.yaml) | ClusterIP service | ✅ Yes |
| [ingress.yaml](ingress.yaml) | External access via NGINX | ⚠️ Optional |
| [hpa.yaml](hpa.yaml) | Horizontal Pod Autoscaler | ⚠️ Optional |
| [servicemonitor.yaml](servicemonitor.yaml) | Prometheus metrics scraping | ⚠️ Optional |

## Configuration Details

### Deployment Configuration

**Key Settings**:
- **Image**: `docker.io/bunkerity/bunkerweb-mcp:latest`
- **Replicas**: 2 (minimum for HA)
- **Workers**: 4 per pod (configurable via `WORKERS` env var)
- **Resources**:
  - Requests: 250m CPU, 256Mi RAM
  - Limits: 1000m CPU, 512Mi RAM

**Health Checks**:
- **Readiness**: `/ready` endpoint (checks dependencies)
- **Liveness**: `/health` endpoint (basic health check)

**Prometheus Metrics**:
- Exposed on port 8080 at `/metrics`
- Annotated for automatic scraping

### Environment Variables

Configure via [configmap.yaml](configmap.yaml):

| Variable | Default | Description |
|----------|---------|-------------|
| `BUNKERWEB_BASE_URL` | - | BunkerWeb API endpoint (required) |
| `WORKERS` | 4 | Uvicorn worker processes |
| `CACHE_ENABLED` | true | Enable response caching (Sprint 2) |
| `RATE_LIMIT_ENABLED` | false | Enable rate limiting (Sprint 2) |
| `SEARCH_MODE` | remote | Semantic search mode |
| `MCP_ENABLE_DNS_REBINDING_PROTECTION` | true | DNS rebinding protection |
| `MCP_ALLOWED_HOSTS` | - | Allowed Host header values |

Full list: See [.env.example](../../.env.example)

### Secret Variables

Configure via `secret.local.yaml` (copy from [secret.yaml](secret.yaml)):

| Variable | Description | Required |
|----------|-------------|----------|
| `BUNKERWEB_API_TOKEN` | Bearer token for BunkerWeb API | Yes (or use Basic auth) |
| `BUNKERWEB_BASIC_USERNAME` | Basic auth username | Alternative to token |
| `BUNKERWEB_BASIC_PASSWORD` | Basic auth password | Alternative to token |
| `BUNKERWEB_WEBSOCKET_TOKEN` | WebSocket authentication | Optional |

## Autoscaling (HPA)

The HorizontalPodAutoscaler automatically scales pods based on:

- **CPU utilization**: Target 70%
- **Memory utilization**: Target 80%
- **Min replicas**: 2
- **Max replicas**: 10

**Scaling behavior**:
- **Scale up**: Fast (max 50% or +2 pods per minute)
- **Scale down**: Conservative (5 min stabilization, max 50% or -1 pod per minute)

Monitor autoscaling:

```bash
kubectl get hpa -n bunkerweb
kubectl describe hpa mcp-bunkerweb -n bunkerweb
```

## Monitoring with Prometheus

The [ServiceMonitor](servicemonitor.yaml) enables automatic metrics collection.

**Metrics exposed**:
- `mcp_tool_calls_total` - Tool invocation counter
- `mcp_tool_duration_seconds` - Tool latency histogram
- `bunkerweb_api_requests_total` - API call counter
- `mcp_cache_hits_total` / `mcp_cache_misses_total` - Cache metrics
- Standard FastAPI metrics (requests, latency, errors)

**Access Grafana dashboards**:
- Import dashboard from [deploy/grafana/dashboards/mcp-bunkerweb.json](../grafana/dashboards/mcp-bunkerweb.json)

## Ingress Configuration

Edit [ingress.yaml](ingress.yaml) to configure external access:

```yaml
spec:
  rules:
    - host: mcp-bunkerweb.example.com  # Change this
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: mcp-bunkerweb
                port:
                  name: http
  tls:
    - hosts:
        - mcp-bunkerweb.example.com  # Change this
      secretName: mcp-bunkerweb-tls  # TLS certificate secret
```

**TLS Certificate**:

Option 1 - cert-manager (recommended):
```bash
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: mcp-bunkerweb-tls
  namespace: bunkerweb
spec:
  secretName: mcp-bunkerweb-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - mcp-bunkerweb.example.com
EOF
```

Option 2 - Manual certificate:
```bash
kubectl create secret tls mcp-bunkerweb-tls \
  --cert=path/to/cert.pem \
  --key=path/to/key.pem \
  -n bunkerweb
```

## Troubleshooting

### Pods not starting

```bash
# Check pod status and events
kubectl describe pod -n bunkerweb -l app=mcp-bunkerweb

# Check logs
kubectl logs -n bunkerweb -l app=mcp-bunkerweb --tail=100

# Common issues:
# - Missing secrets: Apply secret.local.yaml
# - Image pull errors: Verify docker.io/bunkerity/bunkerweb-mcp:latest exists
# - ConfigMap missing: Apply configmap.yaml
```

### Health checks failing

```bash
# Test health endpoints directly
kubectl port-forward -n bunkerweb svc/mcp-bunkerweb 8080:8080
curl http://localhost:8080/health
curl http://localhost:8080/ready

# Check readiness probe logs
kubectl logs -n bunkerweb -l app=mcp-bunkerweb | grep -i "ready\|health"

# Common issues:
# - BunkerWeb API unreachable: Check BUNKERWEB_BASE_URL in ConfigMap
# - Search service unavailable: Check SEARCH_API_URL or set SEARCH_MODE=disabled
```

### HPA not scaling

```bash
# Verify metrics-server is running
kubectl get deployment metrics-server -n kube-system

# Check HPA status
kubectl describe hpa mcp-bunkerweb -n bunkerweb

# View current metrics
kubectl top pods -n bunkerweb
```

### Prometheus not scraping

```bash
# Verify ServiceMonitor is created
kubectl get servicemonitor -n bunkerweb

# Check Prometheus targets
# Access Prometheus UI and check Targets page for mcp-bunkerweb

# Verify pod annotations
kubectl get pod -n bunkerweb -l app=mcp-bunkerweb -o jsonpath='{.items[0].metadata.annotations}'
```

## Upgrade Strategy

### Rolling Update (Zero Downtime)

```bash
# Update image tag in deployment.yaml
kubectl set image deployment/mcp-bunkerweb \
  mcp-bunkerweb=docker.io/bunkerity/bunkerweb-mcp:v0.2.0 \
  -n bunkerweb

# Watch rollout
kubectl rollout status deployment/mcp-bunkerweb -n bunkerweb

# Rollback if needed
kubectl rollout undo deployment/mcp-bunkerweb -n bunkerweb
```

### Update ConfigMap

```bash
# Edit configmap
kubectl edit configmap mcp-bunkerweb-config -n bunkerweb

# Restart pods to pick up changes
kubectl rollout restart deployment/mcp-bunkerweb -n bunkerweb
```

### Update Secrets

```bash
# Update secret
kubectl apply -f secret.local.yaml

# Restart pods to pick up new secrets
kubectl rollout restart deployment/mcp-bunkerweb -n bunkerweb
```

## Security Best Practices

1. **Never commit secrets**: Add `secret.local.yaml` to `.gitignore`
2. **Use RBAC**: Restrict access to the bunkerweb namespace
3. **Enable Network Policies**: Restrict pod-to-pod communication
4. **Use TLS**: Always enable TLS in Ingress for production
5. **Scan images**: Use tools like Trivy to scan container images
6. **Rotate credentials**: Regularly update API tokens and passwords

## Performance Tuning

### High Traffic (>1000 req/s)

```yaml
# deployment.yaml
spec:
  replicas: 4  # Increase replicas
  template:
    spec:
      containers:
        - env:
            - name: WORKERS
              value: "8"  # More workers per pod
          resources:
            limits:
              cpu: "2000m"
              memory: "1Gi"

# hpa.yaml
spec:
  minReplicas: 4
  maxReplicas: 20
```

### Low Traffic (<100 req/s)

```yaml
# deployment.yaml
spec:
  replicas: 1
  template:
    spec:
      containers:
        - env:
            - name: WORKERS
              value: "2"
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"

# Disable HPA
# kubectl delete hpa mcp-bunkerweb -n bunkerweb
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/bunkerity/bunkerweb-mcp/issues
- Documentation: See [../../docs/](../../docs/)
- BunkerWeb Docs: https://docs.bunkerweb.io
