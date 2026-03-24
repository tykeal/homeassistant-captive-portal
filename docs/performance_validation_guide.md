<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Performance Validation Guide — Captive Portal

This guide describes how to manually validate the captive portal's
performance characteristics using standard command-line tools. All
thresholds are derived from the spec success criteria and architecture
principles.

---

## 1. Performance Targets

| Metric | Target | Source |
|--------|--------|--------|
| Container memory | < 128 MB | Operational constraint |
| Container CPU | < 50 % sustained | Operational constraint |
| Health endpoint latency | < 100 ms p95 | Architecture principle |
| Voucher redemption latency | < 100 ms p95 (app layer) | Architecture principle |
| Controller propagation | < 5 s p95 | SC-002 (30 s e2e budget) |
| Concurrent sessions | ≥ 50 simultaneous | Operational constraint |
| DB query time | < 50 ms p95 | Operational constraint |

---

## 2. Prerequisites

### Tools

| Tool | Purpose | Install |
|------|---------|---------|
| `curl` | HTTP requests and timing | Usually pre-installed |
| `wrk` | HTTP load generation | `apt install wrk` or build from source |
| `docker stats` | Container resource monitoring | Docker CE/EE |
| `sqlite3` | Database query profiling | `apt install sqlite3` |
| `jq` | JSON response parsing | `apt install jq` |

### Environment

1. The captive portal container must be running.
2. Note the container name or ID (e.g., `captive-portal`).
3. Note the base URL (e.g., `http://localhost:8080`).

```bash
# Verify the container is running
docker ps --filter name=captive-portal --format '{{.Names}} {{.Status}}'

# Set the base URL for subsequent commands
BASE_URL="http://localhost:8080"
```

---

## 3. Docker Stats Monitoring (Memory & CPU)

### 3.1 Baseline Measurement

Record idle resource consumption before running load tests.

```bash
# Snapshot (one-time)
docker stats captive-portal --no-stream \
  --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

Expected idle baseline:

| Metric | Expected |
|--------|----------|
| Memory | < 64 MB |
| CPU | < 5 % |

### 3.2 Continuous Monitoring During Load

Open a separate terminal and stream stats while running the tests in
sections 4-7.

```bash
# Stream stats every 2 seconds
docker stats captive-portal \
  --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### 3.3 Memory Threshold Validation

After running all load tests, verify memory remains below 128 MB:

```bash
MEM=$(docker stats captive-portal --no-stream \
  --format '{{.MemUsage}}' | cut -d'/' -f1 | tr -d ' ')
echo "Current memory: ${MEM}"
# PASS if value is < 128MiB
```

---

## 4. Health Endpoint Response Time

### 4.1 Single Request

```bash
curl -o /dev/null -s -w "HTTP %{http_code} in %{time_total}s\n" \
  "${BASE_URL}/health"
```

Expected: HTTP 200 in < 0.1 s.

### 4.2 Repeated Measurement (p95)

Run 100 requests and compute the 95th percentile:

```bash
for i in $(seq 1 100); do
  curl -o /dev/null -s -w "%{time_total}\n" "${BASE_URL}/health"
done | sort -n | awk '
  { a[NR] = $1 }
  END {
    p95 = a[int(NR * 0.95)];
    printf "p50: %.4fs  p95: %.4fs  max: %.4fs  n: %d\n",
      a[int(NR * 0.5)], p95, a[NR], NR;
    if (p95 < 0.1) print "PASS"; else print "FAIL - p95 >= 100ms"
  }'
```

### 4.3 Load Test with wrk

```bash
wrk -t2 -c10 -d30s "${BASE_URL}/health"
```

Check the output for:

- **Latency p99** should be < 100 ms
- **Requests/sec** — record as baseline throughput
- **Non-2xx responses** should be 0

---

## 5. Controller API Propagation Timing

This test measures the time from submitting a voucher code to the
controller authorization completing. It requires a running Omada
controller (or mock).

### 5.1 End-to-End Voucher Redemption

```bash
# Create a test voucher (requires admin session cookie)
VOUCHER=$(curl -s -b cookies.txt \
  -X POST "${BASE_URL}/api/vouchers" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -d '{"duration_minutes": 60}' | jq -r '.code')

echo "Test voucher: ${VOUCHER}"

# Time the guest authorization (simulates captive portal submission)
START=$(date +%s%N)
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST "${BASE_URL}/guest/authorize" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=${VOUCHER}"
END=$(date +%s%N)

ELAPSED_MS=$(( (END - START) / 1000000 ))
echo "Propagation time: ${ELAPSED_MS}ms"
# PASS if < 5000ms (5s p95 target)
```

### 5.2 Batch Timing (10 Vouchers)

```bash
for i in $(seq 1 10); do
  VOUCHER=$(curl -s -b cookies.txt \
    -X POST "${BASE_URL}/api/vouchers" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -d '{"duration_minutes": 60}' | jq -r '.code')

  curl -o /dev/null -s -w "%{time_total}\n" \
    -X POST "${BASE_URL}/guest/authorize" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "code=${VOUCHER}"
done | sort -n | awk '
  { a[NR] = $1 }
  END {
    p95 = a[int(NR * 0.95)];
    printf "p50: %.3fs  p95: %.3fs  max: %.3fs\n",
      a[int(NR * 0.5)], p95, a[NR];
    if (p95 < 5.0) print "PASS"; else print "FAIL - p95 >= 5s"
  }'
```

---

## 6. Concurrent Session Handling

### 6.1 Concurrent Health Checks

Test that the application handles concurrent connections without errors:

```bash
wrk -t4 -c50 -d30s "${BASE_URL}/health"
```

**Pass criteria:**

- Zero socket errors
- Zero non-2xx responses
- Latency p99 < 200 ms
- All 50 connections sustained

### 6.2 Concurrent Guest Portal Loads

```bash
wrk -t4 -c50 -d30s "${BASE_URL}/guest/"
```

**Pass criteria:**

- Zero socket errors
- Latency p99 < 500 ms (includes template rendering)

### 6.3 Concurrent API Requests

Test admin API under concurrent load (requires valid session):

```bash
wrk -t2 -c20 -d15s \
  -H "Cookie: session=${SESSION_COOKIE}" \
  "${BASE_URL}/api/grants?status=active"
```

**Pass criteria:**

- Zero non-2xx responses (excluding expected 401 if session expires)
- Latency p99 < 200 ms

---

## 7. Database Query Performance

### 7.1 SQLite Query Timing

Profile queries directly against the database file:

```bash
# Find the database file
DB_PATH=$(docker exec captive-portal find /data -name "*.db" 2>/dev/null | head -1)

# Time a grant lookup query
docker exec captive-portal sqlite3 "${DB_PATH}" \
  ".timer on" \
  "SELECT count(*) FROM access_grant WHERE status = 'active';"

# Time an audit log range query (common admin operation)
docker exec captive-portal sqlite3 "${DB_PATH}" \
  ".timer on" \
  "SELECT count(*) FROM audit_log WHERE timestamp_utc > datetime('now', '-7 days');"

# Time a voucher lookup (guest redemption hot path)
docker exec captive-portal sqlite3 "${DB_PATH}" \
  ".timer on" \
  "EXPLAIN QUERY PLAN SELECT * FROM voucher WHERE code = 'TESTCODE';"
```

**Pass criteria:** All queries < 50 ms.

### 7.2 Index Verification

Ensure the expected indexes exist:

```bash
docker exec captive-portal sqlite3 "${DB_PATH}" \
  ".indexes"
```

Expected indexes on: `audit_log.actor`, `audit_log.action`,
`audit_log.timestamp_utc`, `admin_user.username`, `admin_user.email`.

---

## 8. Running a Full Validation Suite

Execute all checks in sequence. Adjust `BASE_URL` and container name as
needed.

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
CONTAINER="${2:-captive-portal}"

echo "=== 1. Baseline resource usage ==="
docker stats "${CONTAINER}" --no-stream \
  --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "=== 2. Health endpoint (100 requests) ==="
for i in $(seq 1 100); do
  curl -o /dev/null -s -w "%{time_total}\n" "${BASE_URL}/health"
done | sort -n | awk '
  { a[NR]=$1 }
  END {
    p95=a[int(NR*0.95)];
    printf "  p50: %.4fs  p95: %.4fs  max: %.4fs\n", a[int(NR*0.5)], p95, a[NR];
    if (p95<0.1) print "  PASS"; else print "  FAIL"
  }'

echo ""
echo "=== 3. Concurrent connections (wrk) ==="
if command -v wrk &>/dev/null; then
  wrk -t4 -c50 -d15s "${BASE_URL}/health"
else
  echo "  wrk not installed — skipping"
fi

echo ""
echo "=== 4. Post-load resource usage ==="
docker stats "${CONTAINER}" --no-stream \
  --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "=== 5. Memory threshold check ==="
MEM=$(docker stats "${CONTAINER}" --no-stream \
  --format '{{.MemUsage}}' | cut -d'/' -f1 | tr -d ' ')
echo "  Memory: ${MEM}"
echo "  Target: < 128MiB"

echo ""
echo "=== Validation complete ==="
```

---

## 9. Interpreting Results

| Result | Action |
|--------|--------|
| All metrics within targets | Validation passes — record results |
| Memory > 128 MB under load | Investigate memory leaks; check session store cleanup |
| Health p95 > 100 ms | Profile middleware stack; check for blocking I/O |
| Controller propagation > 5 s | Check network latency to Omada controller; review retry queue |
| Socket errors under concurrency | Investigate file descriptor limits (`ulimit -n`) |
| DB queries > 50 ms | Verify indexes exist; check database file size |

---

## 10. Recording Results

Document results in a table for each validation run:

| Date | Tester | Memory (idle) | Memory (load) | Health p95 | Concurrency (errors) | Notes |
|------|--------|---------------|---------------|------------|----------------------|-------|
| | | | | | | |
