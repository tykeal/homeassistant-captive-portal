<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Performance Validation Guide

This guide provides manual validation procedures for verifying that the Captive Portal system meets performance baselines defined in the specification.

## Performance Baselines (p95 Targets)

| Metric | Target (p95) | Load Level | Priority |
|--------|--------------|------------|----------|
| Voucher redemption | ≤800ms | 50 concurrent | HIGH |
| Voucher redemption | ≤900ms | 200 concurrent | MEDIUM |
| Admin login API | ≤300ms | N/A | HIGH |
| Controller propagation | ≤25s | Authorize → Active | HIGH |
| Admin grants list | ≤1500ms | 500 grants | MEDIUM |
| Memory RSS | ≤150MB | Steady state | HIGH |
| CPU 1-min peak | ≤60% | 200 concurrent | MEDIUM |

**Merge Gate**: Performance regressions >10% vs baseline block release.

---

## Prerequisites

### Tools Required
- **Docker**: For resource monitoring (`docker stats`)
- **curl**: For API testing
- **jq**: For JSON parsing (optional but recommended)
- **Apache Bench (`ab`)**: For load testing
- **Python**: For test scripts (optional)

### Test Environment
- Captive Portal running in Docker container
- TP-Link Omada Controller accessible
- Test guest SSID configured
- Admin account created

### Installation
```bash
# Install Apache Bench (Debian/Ubuntu)
sudo apt install apache2-utils

# Install jq
sudo apt install jq

# Verify docker
docker --version
```

---

## Test 1: Memory Usage (RSS)

**Target**: ≤150MB RSS (steady state)

### Procedure

1. **Start Container with Resource Monitoring**
   ```bash
   # Start Captive Portal
   docker-compose up -d captive-portal

   # Wait for startup (30 seconds)
   sleep 30
   ```

2. **Check Baseline Memory Usage**
   ```bash
   # Get container name
   CONTAINER=$(docker ps --filter "name=captive-portal" --format "{{.Names}}")

   # Monitor memory for 60 seconds
   docker stats $CONTAINER --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
   ```

3. **Expected Output**
   ```
   NAME               MEM USAGE / LIMIT     MEM %
   captive-portal     95MiB / 8GiB          1.19%
   ```

4. **Simulate Load (50 concurrent guests)**
   ```bash
   # Run load test script (see Appendix A)
   python3 tests/performance/load_test.py --concurrent 50 --duration 300

   # Monitor memory during load
   docker stats $CONTAINER --no-stream
   ```

5. **Expected Results**
   - **Idle**: 80-110 MB RSS
   - **50 concurrent**: 100-130 MB RSS
   - **Peak**: <150 MB RSS
   - **After load**: Returns to idle within 60 seconds

### Validation
```bash
# Extract RSS value
RSS_MB=$(docker stats $CONTAINER --no-stream --format "{{.MemUsage}}" | cut -d'/' -f1 | sed 's/MiB//')

# Check against target
if (( $(echo "$RSS_MB < 150" | bc -l) )); then
    echo "✅ PASS: Memory usage ${RSS_MB}MB < 150MB"
else
    echo "❌ FAIL: Memory usage ${RSS_MB}MB exceeds 150MB"
fi
```

---

## Test 2: CPU Usage (1-minute peak)

**Target**: ≤60% CPU @ 200 concurrent requests

### Procedure

1. **Monitor CPU Baseline**
   ```bash
   # Idle CPU usage (should be <5%)
   docker stats $CONTAINER --no-stream --format "table {{.Name}}\t{{.CPUPerc}}"
   ```

2. **Simulate 200 Concurrent Requests**
   ```bash
   # Load test for 60 seconds
   ab -n 12000 -c 200 -t 60 \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -p voucher_request.txt \
      http://localhost:8080/portal/voucher
   ```

   **voucher_request.txt** (create this file):
   ```
   voucher_code=TEST123&mac_address=AA:BB:CC:DD:EE:FF
   ```

3. **Monitor CPU During Load**
   ```bash
   # Run in parallel terminal
   while true; do
       docker stats $CONTAINER --no-stream --format "{{.CPUPerc}}" >> cpu_samples.txt
       sleep 1
   done
   ```

4. **Calculate Peak CPU**
   ```bash
   # Find maximum CPU usage from samples
   sort -n cpu_samples.txt | tail -1
   ```

### Expected Results
- **Idle**: 0-5% CPU
- **50 concurrent**: 15-30% CPU
- **200 concurrent**: 40-60% CPU (peak, short bursts acceptable)
- **Sustained**: <45% CPU over 60 seconds

### Validation
```bash
PEAK_CPU=$(sort -n cpu_samples.txt | tail -1 | sed 's/%//')

if (( $(echo "$PEAK_CPU < 60" | bc -l) )); then
    echo "✅ PASS: Peak CPU ${PEAK_CPU}% < 60%"
else
    echo "❌ FAIL: Peak CPU ${PEAK_CPU}% exceeds 60%"
fi
```

---

## Test 3: Voucher Redemption Latency

**Target**: ≤800ms p95 @ 50 concurrent, ≤900ms p95 @ 200 concurrent

### Procedure

1. **Generate Test Voucher**
   ```bash
   # Login as admin
   curl -X POST http://localhost:8080/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin_password"}' \
        -c cookies.txt

   # Create voucher
   curl -X POST http://localhost:8080/api/v1/vouchers \
        -H "Content-Type: application/json" \
        -b cookies.txt \
        -d '{
          "code": "LOADTEST123",
          "max_uses": 1000,
          "expires_at": "2025-12-31T23:59:59Z",
          "duration_minutes": 60
        }' | jq -r '.code'
   ```

2. **Test Single Request Latency**
   ```bash
   curl -w "\nTime: %{time_total}s\n" \
        -X POST http://localhost:8080/portal/voucher \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "voucher_code=LOADTEST123&mac_address=AA:BB:CC:DD:EE:01"
   ```

   **Expected**: <500ms (single request, no load)

3. **Load Test @ 50 Concurrent**
   ```bash
   ab -n 5000 -c 50 \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -p voucher_request.txt \
      http://localhost:8080/portal/voucher
   ```

4. **Analyze Results**
   ```
   Connection Times (ms)
                 min  mean[+/-sd] median   max
   Connect:        0    1   0.5      1       5
   Processing:   120  450  85.2    440     780
   Waiting:      115  445  84.8    435     775
   Total:        121  451  85.3    441     781

   Percentage of the requests served within a certain time (ms)
     50%    441
     66%    485
     75%    520
     80%    545
     90%    625
     95%    720    <- Target: ≤800ms
     98%    755
     99%    770
    100%    781 (longest request)
   ```

5. **Load Test @ 200 Concurrent**
   ```bash
   ab -n 20000 -c 200 \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -p voucher_request.txt \
      http://localhost:8080/portal/voucher
   ```

   **Expected p95**: ≤900ms

### Validation
```bash
# Extract p95 from Apache Bench output
P95=$(ab ... | grep "95%" | awk '{print $2}')

if (( $(echo "$P95 < 800" | bc -l) )); then
    echo "✅ PASS: p95 latency ${P95}ms < 800ms"
else
    echo "⚠️ WARNING: p95 latency ${P95}ms exceeds 800ms (acceptable if <900ms)"
fi
```

---

## Test 4: Admin Login Latency

**Target**: ≤300ms p95

### Procedure

1. **Single Login Request**
   ```bash
   curl -w "\nTime: %{time_total}s\n" \
        -X POST http://localhost:8080/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin_password"}'
   ```

   **Expected**: 150-250ms (bcrypt password hashing overhead)

2. **Load Test (Sequential, Rate-Limited)**
   ```bash
   # Test 100 login requests (rate-limited to 10/min per IP)
   for i in {1..100}; do
       START=$(date +%s%3N)
       curl -s -X POST http://localhost:8080/api/auth/login \
            -H "Content-Type: application/json" \
            -d '{"username":"admin","password":"admin_password"}' > /dev/null
       END=$(date +%s%3N)
       echo "$((END - START))" >> login_latencies.txt
       sleep 0.5  # Respect rate limit
   done
   ```

3. **Calculate p95**
   ```bash
   sort -n login_latencies.txt | awk '{all[NR]=$1} END{print all[int(NR*0.95)]}'
   ```

### Expected Results
- **p50**: 150-200ms
- **p95**: 200-280ms (target: ≤300ms)
- **p99**: 280-350ms

### Validation
```bash
P95=$(sort -n login_latencies.txt | awk '{all[NR]=$1} END{print all[int(NR*0.95)]}')

if (( $(echo "$P95 < 300" | bc -l) )); then
    echo "✅ PASS: Admin login p95 ${P95}ms < 300ms"
else
    echo "❌ FAIL: Admin login p95 ${P95}ms exceeds 300ms"
fi
```

---

## Test 5: Controller Propagation Time

**Target**: ≤25s p95 (authorize → client active)

### Procedure

1. **Authorize Guest Device**
   ```bash
   # Record start time
   START=$(date +%s)

   # Submit authorization
   curl -X POST http://localhost:8080/portal/voucher \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "voucher_code=TEST123&mac_address=AA:BB:CC:DD:EE:FF"
   ```

2. **Poll Controller for Authorization Status**
   ```bash
   # Poll every 2 seconds until authorized
   while true; do
       STATUS=$(curl -s "http://localhost:8080/api/v1/grants?mac=AA:BB:CC:DD:EE:FF" \
                -b cookies.txt | jq -r '.grants[0].status')

       if [ "$STATUS" == "active" ]; then
           END=$(date +%s)
           PROPAGATION_TIME=$((END - START))
           echo "✅ Authorization active: ${PROPAGATION_TIME}s"
           break
       fi

       echo "⏳ Waiting... (status: $STATUS)"
       sleep 2

       # Timeout after 60 seconds
       if (( $(date +%s) - START > 60 )); then
           echo "❌ TIMEOUT: Authorization not active after 60s"
           break
       fi
   done
   ```

3. **Verify Client Internet Access**
   ```bash
   # From guest device (connected to test SSID)
   curl -w "\nHTTP Code: %{http_code}\n" https://www.google.com
   ```

4. **Repeat Test 20 Times**
   ```bash
   # Automated script
   for i in {1..20}; do
       MAC="AA:BB:CC:DD:EE:$(printf "%02X" $i)"
       # Run authorization + polling (save propagation time)
       echo "$PROPAGATION_TIME" >> propagation_times.txt
   done
   ```

5. **Calculate p95**
   ```bash
   sort -n propagation_times.txt | awk '{all[NR]=$1} END{print all[int(NR*0.95)]}'
   ```

### Expected Results
- **p50**: 12-18s (typical Omada AP sync time)
- **p95**: 18-24s (target: ≤25s)
- **p99**: 24-30s
- **Max**: <40s (retry queue timeout)

### Validation
```bash
P95=$(sort -n propagation_times.txt | awk '{all[NR]=$1} END{print all[int(NR*0.95)]}')

if (( $(echo "$P95 < 25" | bc -l) )); then
    echo "✅ PASS: Controller propagation p95 ${P95}s < 25s"
else
    echo "❌ FAIL: Controller propagation p95 ${P95}s exceeds 25s"
fi
```

---

## Test 6: Admin Grants List (500 Grants)

**Target**: ≤1500ms p95

### Procedure

1. **Generate Test Data (500 Grants)**
   ```bash
   # SQL insert script
   sqlite3 /data/captive_portal.db << EOF
   BEGIN TRANSACTION;
   INSERT INTO access_grant (id, mac_address, expires_at, booking_code, created_at)
   SELECT
       lower(hex(randomblob(16))),
       printf('%02X:%02X:%02X:%02X:%02X:%02X',
              abs(random() % 256), abs(random() % 256), abs(random() % 256),
              abs(random() % 256), abs(random() % 256), abs(random() % 256)),
       datetime('now', '+' || (abs(random() % 48) + 1) || ' hours'),
       'BOOKING' || abs(random() % 10000),
       datetime('now', '-' || (abs(random() % 720) + 1) || ' minutes')
   FROM generate_series(1, 500);
   COMMIT;
   EOF
   ```

2. **Test Grants List Endpoint**
   ```bash
   # Measure response time
   curl -w "\nTime: %{time_total}s\n" \
        -X GET "http://localhost:8080/api/v1/grants?page=1&page_size=50" \
        -b cookies.txt
   ```

3. **Load Test (10 Concurrent Admin Users)**
   ```bash
   ab -n 1000 -c 10 \
      -C "session_id=admin_session_token" \
      http://localhost:8080/api/v1/grants?page=1&page_size=50
   ```

4. **Analyze Results**
   ```
   Percentage of the requests served within a certain time (ms)
     50%    850
     75%   1100
     90%   1350
     95%   1450    <- Target: ≤1500ms
     99%   1550
   ```

### Expected Results
- **p50**: 700-1000ms
- **p95**: 1200-1450ms (target: ≤1500ms)
- **Note**: Latency increases linearly with page_size

### Validation
```bash
P95=$(ab ... | grep "95%" | awk '{print $2}')

if (( $(echo "$P95 < 1500" | bc -l) )); then
    echo "✅ PASS: Grants list p95 ${P95}ms < 1500ms"
else
    echo "❌ FAIL: Grants list p95 ${P95}ms exceeds 1500ms"
fi
```

---

## Test 7: Continuous Load (Stability Test)

**Objective**: Verify system stability under sustained load for 1 hour

### Procedure

1. **Start Load Generator**
   ```bash
   # Run in background
   ab -n 360000 -c 50 -t 3600 \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -p voucher_request.txt \
      http://localhost:8080/portal/voucher > load_test_results.txt &
   ```

2. **Monitor Resources**
   ```bash
   # Log CPU and memory every 10 seconds
   while true; do
       TIMESTAMP=$(date +%s)
       CPU=$(docker stats $CONTAINER --no-stream --format "{{.CPUPerc}}" | sed 's/%//')
       MEM=$(docker stats $CONTAINER --no-stream --format "{{.MemUsage}}" | cut -d'/' -f1 | sed 's/MiB//')
       echo "$TIMESTAMP,$CPU,$MEM" >> resource_samples.csv
       sleep 10
   done
   ```

3. **Check for Memory Leaks**
   ```bash
   # Plot memory usage over time (requires gnuplot)
   gnuplot << EOF
   set terminal png size 1200,600
   set output 'memory_over_time.png'
   set datafile separator ','
   set xlabel 'Time (s)'
   set ylabel 'Memory (MB)'
   plot 'resource_samples.csv' using 1:3 with lines title 'RSS'
   EOF
   ```

4. **Analyze Results**
   - **Memory Growth**: Should be <10MB over 1 hour (no leaks)
   - **CPU Stability**: Should remain steady (no spikes)
   - **Error Rate**: <0.1% failed requests
   - **Response Time**: p95 should not degrade >10% over time

### Validation
```bash
# Check for memory growth
MEM_START=$(head -1 resource_samples.csv | cut -d',' -f3)
MEM_END=$(tail -1 resource_samples.csv | cut -d',' -f3)
MEM_GROWTH=$(echo "$MEM_END - $MEM_START" | bc)

if (( $(echo "$MEM_GROWTH < 10" | bc -l) )); then
    echo "✅ PASS: Memory growth ${MEM_GROWTH}MB < 10MB (no leak detected)"
else
    echo "❌ FAIL: Memory growth ${MEM_GROWTH}MB suggests memory leak"
fi
```

---

## Test 8: Metrics Validation

**Objective**: Verify Prometheus metrics are accurate and complete

### Procedure

1. **Access Metrics Endpoint**
   ```bash
   curl -b cookies.txt http://localhost:8080/metrics
   ```

2. **Verify Metric Presence**
   ```bash
   # Check for required metrics
   METRICS=(
       "captive_portal_active_sessions"
       "captive_portal_controller_latency_seconds"
       "captive_portal_auth_failures_total"
       "captive_portal_voucher_redemptions_total"
   )

   for metric in "${METRICS[@]}"; do
       if curl -s -b cookies.txt http://localhost:8080/metrics | grep -q "$metric"; then
           echo "✅ $metric present"
       else
           echo "❌ $metric missing"
       fi
   done
   ```

3. **Validate Metric Accuracy**
   ```bash
   # Authorize 5 guests
   for i in {1..5}; do
       curl -X POST http://localhost:8080/portal/voucher \
            -d "voucher_code=TEST123&mac_address=AA:BB:CC:DD:EE:0$i"
   done

   # Check active_sessions metric
   ACTIVE_SESSIONS=$(curl -s -b cookies.txt http://localhost:8080/metrics \
                     | grep "captive_portal_active_sessions" \
                     | awk '{print $2}')

   if [ "$ACTIVE_SESSIONS" -ge 5 ]; then
       echo "✅ Active sessions metric accurate: $ACTIVE_SESSIONS"
   else
       echo "❌ Active sessions metric incorrect: $ACTIVE_SESSIONS (expected ≥5)"
   fi
   ```

---

## Performance Regression Checklist

Before each release, verify:

- [ ] Memory RSS < 150MB under load
- [ ] CPU peak < 60% @ 200 concurrent
- [ ] Voucher redemption p95 < 800ms @ 50 concurrent
- [ ] Admin login p95 < 300ms
- [ ] Controller propagation p95 < 25s
- [ ] Grants list p95 < 1500ms (500 grants)
- [ ] No memory leaks (1-hour stability test)
- [ ] All Prometheus metrics present and accurate
- [ ] No >10% performance regression vs previous release

---

## Troubleshooting Performance Issues

### High Memory Usage
- **Check**: Orphaned sessions in session store
- **Solution**: Verify session cleanup task running
- **Command**: `SELECT COUNT(*) FROM admin_session WHERE expires_at < NOW();`

### High CPU Usage
- **Check**: Database query performance
- **Solution**: Run `ANALYZE` on SQLite, add missing indexes
- **Command**: `sqlite3 /data/captive_portal.db "ANALYZE;"`

### Slow Controller Propagation
- **Check**: Network latency to controller
- **Solution**: Ensure Captive Portal and controller on same network segment
- **Test**: `ping -c 10 controller-ip`

### API Latency Spikes
- **Check**: Controller API timeouts
- **Solution**: Increase `OMADA_TIMEOUT_SECONDS`
- **Monitoring**: Check `captive_portal_controller_latency_seconds` metric

---

## Appendix A: Load Test Script

Save as `tests/performance/load_test.py`:

```python
#!/usr/bin/env python3
import asyncio
import httpx
import time
from statistics import mean, median

async def single_request(client, url, data):
    start = time.time()
    try:
        response = await client.post(url, data=data)
        latency = (time.time() - start) * 1000
        return {"success": True, "latency": latency, "status": response.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def run_load_test(url, concurrent, duration):
    async with httpx.AsyncClient() as client:
        results = []
        start_time = time.time()

        while time.time() - start_time < duration:
            tasks = []
            for i in range(concurrent):
                data = {
                    "voucher_code": "LOADTEST123",
                    "mac_address": f"AA:BB:CC:DD:EE:{i % 256:02X}"
                }
                tasks.append(single_request(client, url, data))

            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

        # Calculate statistics
        latencies = [r["latency"] for r in results if r["success"]]
        print(f"Total requests: {len(results)}")
        print(f"Successful: {len(latencies)}")
        print(f"Mean latency: {mean(latencies):.2f}ms")
        print(f"Median latency: {median(latencies):.2f}ms")
        print(f"p95 latency: {sorted(latencies)[int(len(latencies)*0.95)]:.2f}ms")

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/portal/voucher"
    asyncio.run(run_load_test(url, concurrent=50, duration=60))
```

---

**End of Performance Validation Guide**
