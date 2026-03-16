# Load Testing Guide - MCP BunkerWeb

## 🎯 Overview

This guide explains how to run load tests on the MCP BunkerWeb server to validate performance and identify scalability limits.

## 📋 Prerequisites

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Or install only Locust
pip install locust
```

## 📊 Available Test Types

### Test 1: Simple Performance Test
**File**: `simple_loadtest.py`
**Scenario**: Basic calls to `/tools` and `/health`
**Usage**:
```bash
locust -f ./tests/simple_loadtest.py --host http://localhost:8080 \
       --users 100 --spawn-rate 10 --run-time 1m --headless
```

### Test 2: Realistic MCP Scenarios
**File**: `locustfile.py`
**Scenarios**:
- MCPUser: Typical user behavior
- CacheTestUser: Cache efficiency test
- ReadOnlyUser: Read-only operations
- WriteHeavyUser: Read/write mix

**Usage**:
```bash
locust -f ./tests/locustfile.py --host http://localhost:8080 \
       --users 100 --spawn-rate 10 --run-time 5m --headless
```

### Test 3: Interactive Test (With UI)
**Usage**:
```bash
# 1. Start the server
uvicorn bunkerweb_mcp.main:app --port 8080 --workers 4

# 2. In another terminal, start Locust
locust -f ./tests/locustfile.py --host http://localhost:8080

# 3. Open http://localhost:8089 in your browser
# 4. Configure number of users and launch the test
```

## 🔬 Test Scenarios

### Scenario 1: Stability Test
**Objective**: Verify stability under continuous load

```bash
locust -f ./tests/simple_loadtest.py \
       --host http://localhost:8080 \
       --users 50 \
       --spawn-rate 5 \
       --run-time 30m \
       --headless
```

**Metrics to monitor**:
- Failure rate must stay at 0%
- P95 latency must remain stable
- No memory leaks

### Scenario 2: Scalability Test
**Objective**: Find the breaking point

```bash
# Progressive test
for USERS in 50 100 200 500 1000; do
    echo "Testing with $USERS users..."
    locust -f ./tests/simple_loadtest.py \
           --host http://localhost:8080 \
           --users $USERS \
           --spawn-rate 50 \
           --run-time 2m \
           --headless \
           --html report-$USERS-users.html
    sleep 10
done
```

### Scenario 3: Cache Test
**Objective**: Measure cache efficiency

```bash
# With cache enabled (default)
CACHE_ENABLED=true locust -f ./tests/locustfile.py \
       --host http://localhost:8080 \
       --users 100 \
       --run-time 5m \
       --headless \
       --html report-with-cache.html

# Without cache (for comparison)
CACHE_ENABLED=false locust -f ./tests/locustfile.py \
       --host http://localhost:8080 \
       --users 100 \
       --run-time 5m \
       --headless \
       --html report-no-cache.html
```

**Expected comparison**:
- With cache: P95 < 100ms
- Without cache: P95 ~200-300ms

### Scenario 4: Rate Limiting Test
**Objective**: Verify that rate limiting works

```bash
# Enable rate limiting
RATE_LIMIT_ENABLED=true \
RATE_LIMIT_TOOLS=30/minute \
locust -f ./tests/simple_loadtest.py \
       --host http://localhost:8080 \
       --users 10 \
       --spawn-rate 10 \
       --run-time 2m \
       --headless
```

**Expected results**:
- HTTP 429 errors after limit exceeded
- Error rate > 0% if load exceeds limits

## 📈 Results Interpretation

### Key Metrics

| Metric | Good | Acceptable | Problematic |
|----------|-----|------------|---------------|
| **Throughput** | > 70 req/s | 40-70 req/s | < 40 req/s |
| **P95 Latency** | < 100ms | 100-200ms | > 200ms |
| **P99 Latency** | < 150ms | 150-300ms | > 300ms |
| **Failure Rate** | 0% | < 1% | > 1% |

### HTML Report Analysis

The generated HTML report contains:
1. **Charts**: Real-time graphs of throughput and latency
2. **Statistics**: Detailed table by endpoint
3. **Response Times**: Response time distribution
4. **Failures**: List of encountered errors

**Points of attention**:
- Progressive latency increase = bottleneck
- Error rate > 0% = stability or resource problem
- Throughput plateaus = scalability limit reached

## 🔧 Optimization Based on Results

### If P95 > 100ms
1. Verify that cache is enabled (`CACHE_ENABLED=true`)
2. Increase number of workers
3. Check CPU/memory resources

### If Throughput < 70 req/s (1 worker)
1. Profile code with `py-spy` or `cProfile`
2. Check for blocking I/O
3. Increase workers

### If Failure Rate > 0%
1. Check server logs
2. Increase resources (CPU/memory)
3. Verify connectivity to BunkerWeb backend

### If Latency increases over time
1. Check for memory leaks
2. Profile with `memory_profiler`
3. Check garbage collection

## 📊 Example Results

### Configuration: 1 worker, cache enabled
```
Users: 100
Duration: 60s
Throughput: 73.90 req/s
P95 Latency: 80ms
Failure Rate: 0%
```
✅ Excellent for development environment

### Configuration: 4 workers, cache enabled (projection)
```
Users: 400
Duration: 5m
Throughput: ~300 req/s (projected)
P95 Latency: < 100ms (projected)
Failure Rate: 0%
```
✅ Suitable for medium-load production

### Configuration: 16 workers, cache enabled (projection)
```
Users: 1000
Duration: 10m
Throughput: ~1200 req/s (projected)
P95 Latency: < 100ms (projected)
Failure Rate: 0%
```
✅ Suitable for high-load production

## 🛠️ Troubleshooting

### Problem: "Connection refused"
```bash
# Check that the server is running
lsof -i :8080

# Start the server if necessary
uvicorn bunkerweb_mcp.main:app --port 8080
```

### Problem: "Too many open files"
```bash
# Increase open files limit
ulimit -n 65536
```

## 📝 Best Practices

1. **Always test in isolated environment**
   - Not on a production server
   - Dedicated machine if possible

2. **Do a warm-up**
   ```bash
   # A few requests before the test
   for i in {1..10}; do curl http://localhost:8080/tools; done
   ```

3. **Test with different configurations**
   - 1, 2, 4, 8 workers
   - Cache enabled/disabled
   - Rate limiting enabled/disabled

4. **Save reports**
   ```bash
   # All reports are in load-test-reports/
   ls -lh load-test-reports/
   ```

5. **Compare with baseline**
   - Always have a reference test
   - Compare after each change
