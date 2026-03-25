<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Troubleshooting Guide

This guide covers diagnostics, common problems, and solutions for the Captive
Portal Guest Access system. For system design context, see
[Architecture Overview](architecture_overview.md). For integration-specific
setup, see [HA Integration Guide](ha_integration_guide.md) and
[TP-Link Omada Setup](tp_omada_setup.md).

---

## Table of Contents

- [Quick Diagnostics Checklist](#quick-diagnostics-checklist)
- [Health and Readiness Checks](#health-and-readiness-checks)
- [Logging and Debug Mode](#logging-and-debug-mode)
- [Guest Authorization Problems](#guest-authorization-problems)
- [Admin UI Access Issues](#admin-ui-access-issues)
- [TP-Link Omada Controller Integration](#tp-link-omada-controller-integration)
- [Home Assistant Integration](#home-assistant-integration)
- [Network Connectivity Diagnostics](#network-connectivity-diagnostics)
- [Database Issues](#database-issues)
- [Performance Debugging](#performance-debugging)
- [Security and Session Issues](#security-and-session-issues)
- [Captive Portal Detection](#captive-portal-detection)
- [FAQ](#faq)

---

## Quick Diagnostics Checklist

Run through these checks first to narrow down the problem area:

| Check | Command | Expected |
|-------|---------|----------|
| Portal is running | `curl -s http://localhost:8080/api/health` | `{"status": "ok", ...}` |
| Portal is ready | `curl -s http://localhost:8080/api/ready` | `{"status": "ok", ...}` |
| Omada reachable | `curl -sk https://<omada_ip>:8043` | HTML or JSON response |
| HA reachable (addon) | `curl -sH "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/` | JSON response |
| HA reachable (standalone) | `curl -sH "Authorization: Bearer <token>" https://<ha_host>:8123/api/` | `{"message": "API running."}` |
| Database exists | `ls -la /data/captive_portal.db` | File present with non-zero size |
| Logs accessible | `docker logs <container>` or HA addon log viewer | Log output visible |

---

## Health and Readiness Checks

### Startup Probe — `/api/health`

Returns basic service status:

```bash
curl -s http://localhost:8080/api/health | python3 -m json.tool
```

**Healthy response:**

```json
{
  "status": "ok",
  "timestamp": "2025-03-25T14:30:00.123456+00:00"
}
```

**If `/api/health` does not respond:**

- The application process is not running or has crashed.
- Check container/addon logs for startup errors.
- Verify port 8080 is not blocked or already in use:

```bash
ss -tlnp | grep 8080
```

### Readiness Probe — `/api/ready`

Checks that downstream dependencies (database) are accessible. If
`/api/health` returns OK but `/api/ready` does not, the application is running but
cannot serve requests because a dependency is down.

```bash
curl -s http://localhost:8080/api/ready | python3 -m json.tool
```

**Degraded response example:**

```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "omada_controller": "unreachable"
  }
}
```

---

## Logging and Debug Mode

### Enabling Debug Logging

Set the log level in your configuration:

**Home Assistant addon** (`Configuration` tab):

```yaml
log_level: DEBUG
```

**Standalone (environment variable):**

```bash
export LOG_LEVEL=DEBUG
```

After changing, restart the addon or application.

> **Warning:** DEBUG level logs request/response payloads and may impact
> performance under heavy load. Use only during active troubleshooting.

### Log Locations

| Deployment | Location |
|------------|----------|
| HA addon | **Settings → Add-ons → Captive Portal Guest Access → Log** tab |
| Docker standalone | `docker logs captive-portal` or `docker logs -f captive-portal` |
| Direct execution | stdout/stderr of the `uvicorn` process |

### Key Log Messages to Look For

**Normal startup sequence:**

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
INFO:     Starting HA poller
INFO:     Retry queue service started
```

**Warning indicators:**

```
WARNING:  Retry queue already running
WARNING:  Skipping event with missing timestamps (event_index=2, integration_id=rental-1)
WARNING:  Skipping event with no valid identifiers (event_index=3, integration_id=rental-1)
WARNING:  Retry authorize failed for AA:BB:CC:DD:EE:FF: Connection refused
```

**Error indicators:**

```
ERROR:    HA polling error (error=ConnectionError, error_count=3, backoff_seconds=240)
ERROR:    Max retries (3) exceeded for authorize on AA:BB:CC:DD:EE:FF
```

### Filtering Logs

```bash
# Show only errors and warnings
docker logs captive-portal 2>&1 | grep -E "ERROR|WARNING"

# Show Omada-related messages
docker logs captive-portal 2>&1 | grep -i omada

# Show HA poller messages
docker logs captive-portal 2>&1 | grep -i "ha poll"

# Follow logs in real time
docker logs -f captive-portal 2>&1 | grep --line-buffered "ERROR"
```

---

## Guest Authorization Problems

### Guest Sees "Invalid Code" on Submission

**Symptoms:** Guest enters a voucher or booking code on the portal page and
receives an error indicating the code is invalid.

**Possible causes and solutions:**

1. **Code does not exist:**
   - Verify the voucher exists in the admin UI under **Vouchers**.
   - Verify the booking code exists in HA entity attributes.
   - Check for typos — codes are case-insensitive on input but must match
     stored values after normalization.

2. **Voucher exhausted (all uses consumed):**
   - Check remaining uses in the admin UI. Create a new voucher if needed:

     ```bash
     curl -s -X POST http://localhost:8080/api/v1/vouchers \
       -H "Cookie: session=<admin_session>" \
       -H "Content-Type: application/json" \
       -d '{"max_uses": 5, "duration_hours": 24}'
     ```

3. **Booking outside valid window:**
   - The booking code is only valid between `check_in - grace_before` and
     `check_out + grace_after`.
   - Check the HA entity attributes for `check_in` and `check_out` timestamps.
   - Adjust grace periods in configuration if needed:

     ```yaml
     ha_grace_period_before_hours: 1
     ha_grace_period_after_hours: 2
     ```

   - **Error (HTTP 410):** `Booking outside valid window` — the current time
     falls outside the grace-adjusted booking window.

4. **HA integration unavailable:**
   - **Error (HTTP 503):** `Integration unavailable` — the HA poller cannot
     reach Home Assistant or has no cached events.
   - Check HA connectivity (see [Home Assistant Integration](#home-assistant-integration)).

### Guest Sees "Too Many Attempts" (HTTP 429)

**Symptom:** Portal returns `429 Too Many Requests`.

**Cause:** The guest's IP has exceeded the rate limit (default: 5 attempts per
60 seconds).

**Solutions:**

- Wait for the rate limit window to expire (default: 60 seconds).
- If this is a legitimate usage pattern, increase the limits:

  ```yaml
  rate_limit_attempts: 10
  rate_limit_window_seconds: 60
  ```

- Check if multiple guests share a NAT IP (common in hotel/rental settings).
  Increase the limit accordingly.

### Guest Authorized but No Internet Access

**Symptoms:** The portal shows "Authorization successful" but the guest device
still cannot access the internet.

**Diagnose:**

1. Verify the grant was created:

   ```bash
   curl -s http://localhost:8080/api/v1/grants \
     -H "Cookie: session=<admin_session>" | python3 -m json.tool
   ```

   Look for the guest's MAC address with `status: "active"`.

2. Verify the controller received the authorization:
   - Log in to the Omada controller web UI.
   - Navigate to **Insight → Client List** and find the guest's MAC address.
   - Check the client's authorization status.

3. Check for Omada errors in the logs:

   ```bash
   docker logs captive-portal 2>&1 | grep -i "omada\|authorize\|retry"
   ```

4. Common causes:
   - **Omada controller rejected the request** — check Omada operator account
     permissions (see [TP-Link Omada Setup](tp_omada_setup.md)).
   - **MAC address mismatch** — the client's MAC on the captive portal VLAN
     differs from its MAC on the guest VLAN (common with MAC randomization).
   - **Retry queue still processing** — the authorization may be queued. Check
     logs for retry messages.

### Duplicate Grant Error (HTTP 409)

**Symptom:** Guest receives `409 Conflict` when submitting a booking code.

**Cause:** An active grant already exists for this booking code and device.

**Solution:**

- The guest already has access. Direct them to try browsing the internet.
- If the previous grant needs to be replaced, revoke it from the admin UI first:

  ```bash
  curl -s -X POST http://localhost:8080/api/v1/grants/<grant_id>/revoke \
    -H "Cookie: session=<admin_session>"
  ```

---

## Admin UI Access Issues

### Cannot Log In — "Invalid Credentials"

**Possible causes:**

1. **Wrong username or password:**
   - Verify the credentials match your configuration.
   - Passwords are hashed with Argon2id (or bcrypt for legacy accounts) — they
     cannot be recovered, only reset.

2. **No admin account exists (first-time setup):**
   - Bootstrap the initial admin account:

     ```bash
     curl -s -X POST http://localhost:8080/api/admin/auth/bootstrap \
       -H "Content-Type: application/json" \
       -d '{"username": "admin", "password": "YourSecurePassword123!"}'
     ```

   - The bootstrap endpoint only works when no admin accounts exist.

3. **Account locked or session expired:**
   - Admin sessions expire after the configured lifetime (default: 24 hours).
   - Log in again to create a new session.

### CSRF Token Validation Failed (HTTP 403)

**Symptom:** State-changing requests (POST/PUT/DELETE) fail with
`403 Forbidden` and a CSRF-related error.

**Possible causes:**

1. **Browser cookies blocked or expired:**
   - Clear cookies for the portal domain and log in again.
   - Ensure third-party cookies are not being blocked.

2. **Reverse proxy stripping headers:**
   - The CSRF system uses double-submit cookies. Ensure your reverse proxy
     passes the `Cookie` header and does not rewrite `Set-Cookie` responses.
   - Required headers to forward: `Cookie`, `X-CSRF-Token`, `Host`.

3. **Mixed HTTP/HTTPS:**
   - CSRF cookies are set with `Secure` flag when served over HTTPS.
   - Do not mix HTTP and HTTPS access — use one consistently.

### Admin UI Returns 403 — Permission Denied

**Symptom:** Logged-in admin can view the dashboard but certain actions fail
with `403 Forbidden`.

**Cause:** The admin account's role lacks the required permission. The RBAC
system is deny-by-default.

**Role capabilities:**

| Action | viewer | auditor | operator | admin |
|--------|--------|---------|----------|-------|
| View health status | ✅ | ✅ | ✅ | ✅ |
| View audit logs | ❌ | ✅ | ❌ | ✅ |
| View grants | ❌ | ✅ | ✅ | ✅ |
| Create/redeem vouchers | ❌ | ❌ | ✅ | ✅ |
| Extend/revoke grants | ❌ | ❌ | ✅ | ✅ |
| Manage accounts | ❌ | ❌ | ❌ | ✅ |
| Change configuration | ❌ | ❌ | ❌ | ✅ |

See [Permissions Matrix](permissions_matrix.md) for the full reference.

**Solution:** Have an `admin`-role user upgrade the account's role.

---

## TP-Link Omada Controller Integration

### Connection Refused or Timeout

**Symptoms:**

```
OmadaRetryExhaustedError: Connection error after 3 attempts: [Errno 111] Connection refused
OmadaRetryExhaustedError: Timeout after 3 attempts: ReadTimeout
```

**Diagnostics:**

```bash
# Test basic connectivity
curl -sk https://<omada_ip>:8043

# Test from inside the container
docker exec captive-portal curl -sk https://<omada_ip>:8043

# Check DNS resolution
docker exec captive-portal nslookup <omada_hostname>

# Check firewall rules (from the host)
iptables -L -n | grep 8043
```

**Solutions:**

1. Verify the `omada_url` configuration is correct (include `https://` and
   port `8043`).
2. Ensure the Omada controller is running and accessible from the portal's
   network.
3. Check that port 8043 is not blocked by a firewall between the portal host
   and the controller.
4. If using a hostname, verify DNS resolution works from inside the container.
5. Increase timeout if the controller is slow to respond:

   ```yaml
   omada_timeout_seconds: 30
   ```

### Authentication Failed

**Symptoms:**

```
OmadaAuthenticationError: Omada login failed: Invalid username or password
OmadaAuthenticationError: HTTP 401: Unauthorized
```

**Diagnostics:**

```bash
# Verify credentials by logging in manually
curl -sk -X POST https://<omada_ip>:8043/<controller_id>/api/v2/hotspot/login \
  -H "Content-Type: application/json" \
  -d '{"name": "<omada_username>", "password": "<omada_password>"}'
```

**Solutions:**

1. Verify `omada_username` and `omada_password` in your configuration.
2. The account **must** be a Hotspot Operator account, not a regular admin.
   See [TP-Link Omada Setup](tp_omada_setup.md) for account creation steps.
3. Check if the Omada controller password policy has expired the credentials.
4. Ensure the account has not been disabled in the controller.

### CSRF Token Not Found

**Symptom:**

```
OmadaAuthenticationError: CSRF token not found in login response
```

**Cause:** The Omada controller API response format has changed or the login
succeeded but returned an unexpected payload.

**Solutions:**

1. Verify the Omada controller firmware version is compatible. The adapter
   expects the v2 Hotspot API (`/api/v2/hotspot/`).
2. Update the Omada controller to a supported firmware version.
3. Check the Omada controller logs for errors during the login request.

### Session Cookie Not Found

**Symptom:**

```
OmadaAuthenticationError: Session cookie not found in response
```

**Cause:** The Omada controller did not return a `TPOMADA_SESSIONID` or
`TPEAP_SESSIONID` cookie in the login response.

**Solutions:**

1. Verify the controller is an Omada SDN controller (not a standalone EAP
   management interface).
2. Check if SSL certificate verification is failing silently. Try:

   ```yaml
   omada_verify_ssl: false
   ```

   > **Warning:** Only disable SSL verification for debugging. Re-enable in
   > production or configure a trusted certificate.

### Authorization Rejected by Controller

**Symptom:** Grant is created in the portal database, but the Omada controller
rejects the authorization request.

```
OmadaClientError: Client error 400: Invalid parameter
OmadaClientError: Client error 403: Insufficient privileges
```

**Diagnostics:**

1. Check that the `omada_site` value is correct and **case-sensitive** (e.g.,
   `Default`, not `default`).
2. Verify the Hotspot Operator account has the `External Portal Auth`
   privilege for the target site.
3. Confirm the MAC address format is correct (`AA:BB:CC:DD:EE:FF`).

### Retry Exhaustion

**Symptom:**

```
OmadaRetryExhaustedError: Server error after 3 attempts: 502
OmadaRetryExhaustedError: Exhausted 3 attempts
```

**Cause:** The controller returned 5xx errors or connection failures on all
retry attempts (exponential backoff: 2s, 4s, 8s…).

**Solutions:**

1. Check the Omada controller's health — it may be overloaded or restarting.
2. Check the controller's system logs for internal errors.
3. If the controller is under maintenance, the retry queue service will
   automatically re-attempt failed operations once the controller recovers.
4. Monitor the retry queue in logs:

   ```bash
   docker logs captive-portal 2>&1 | grep "Retry\|retry\|Enqueued"
   ```

---

## Home Assistant Integration

### HA Poller Not Starting

**Symptom:** No `Starting HA poller` message in logs. Booking codes from HA
are never available.

**Diagnostics:**

```bash
docker logs captive-portal 2>&1 | grep -i "ha poller"
```

**Solutions:**

1. Verify the HA poller is enabled:

   ```yaml
   ha_poller_enabled: true
   ```

2. Ensure HA connection settings are configured:

   - **Addon mode:** `ha_url` defaults to `http://supervisor/core` and
     `ha_token` is auto-configured via the Supervisor API.
   - **Standalone mode:** Both `ha_url` and `ha_token` must be set:

     ```yaml
     ha_url: "https://homeassistant.local:8123"
     ha_token: "eyJhbGciOiJIUzI1NiIsIn..."
     ```

3. Verify the `homeassistant_api: true` flag is set in the addon configuration
   if running as an HA addon.

### HA Polling Errors with Backoff

**Symptom:**

```
ERROR: HA polling error (error=ConnectionError, error_count=3, backoff_seconds=240)
```

The poller uses exponential backoff (max 300 seconds) on consecutive failures.

**Diagnostics:**

```bash
# Test HA API from inside the container (addon mode)
docker exec captive-portal curl -s \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/core/api/

# Test HA API (standalone mode)
curl -s -H "Authorization: Bearer <long_lived_token>" \
  https://<ha_host>:8123/api/
```

**Expected response:**

```json
{"message": "API running."}
```

**Solutions:**

1. **Connection refused:** HA is not running or the URL is wrong.
2. **401 Unauthorized:** The access token is invalid or expired. Generate a
   new long-lived access token in HA under
   **Profile → Security → Long-Lived Access Tokens**.
3. **Timeout:** HA is overloaded or network is slow. Increase the polling
   interval:

   ```yaml
   ha_poller_interval_seconds: 120
   ```

4. **SSL error (standalone):** Verify the HA certificate or use `http://` if
   HA is accessed over a local network without TLS.

### No Booking Entities Discovered

**Symptom:** HA poller runs successfully but no booking events appear.

**Diagnostics:**

```bash
# Force an immediate poll
curl -s -X POST http://localhost:8080/api/v1/integrations/ha/poll \
  -H "Cookie: session=<admin_session>"

# Check discovered entities
curl -s http://localhost:8080/api/v1/integrations/ha/entities \
  -H "Cookie: session=<admin_session>" | python3 -m json.tool
```

**Solutions:**

1. **Entity pattern mismatch:** The default pattern is `sensor.rental_*`.
   Verify your Rental Control entities match:

   ```bash
   curl -s -H "Authorization: Bearer <token>" \
     http://<ha_host>:8123/api/states | \
     python3 -c "import sys,json; [print(e['entity_id']) for e in json.load(sys.stdin) if 'rental' in e['entity_id'].lower()]"
   ```

   Adjust the pattern:

   ```yaml
   ha_entity_pattern: "sensor.rental_*"
   ```

2. **Missing booking code attribute:** The entity must have at least one of
   the configured booking code attributes. Default lookup order:
   - `booking_code` (primary)
   - `checkin_code` (fallback)
   - `access_code` (fallback)

   Customize:

   ```yaml
   ha_booking_code_attributes: ["booking_code", "confirmation_number"]
   ```

3. **Entity state not `active` or `upcoming`:** Only entities with appropriate
   states are processed.

### Events Skipped with Warnings

**Symptom:**

```
WARNING: Skipping event with missing timestamps (event_index=2, integration_id=rental-1)
WARNING: Skipping event with no valid identifiers (event_index=3, integration_id=rental-1)
```

**Cause:** The Rental Control entity is missing required attributes.

**Required attributes:**

| Attribute | Purpose |
|-----------|---------|
| `check_in` | Booking start time (ISO 8601) |
| `check_out` | Booking end time (ISO 8601) |
| At least one of `booking_code`, `checkin_code`, `access_code` | Guest identifier |

**Solution:** Check the Rental Control integration in HA and ensure the
calendar or booking source provides complete event data. See
[HA Integration Guide](ha_integration_guide.md) for entity setup.

### Booking Code Works in HA but Fails in Portal

**Symptom:** The booking code is visible in HA entity attributes but the portal
rejects it.

**Diagnostics:**

1. Check if the event has been cached by the poller:

   ```bash
   curl -s http://localhost:8080/api/v1/integrations/ha/entities \
     -H "Cookie: session=<admin_session>" | python3 -m json.tool
   ```

2. Check the grace period window. The portal validates that the current time
   falls within `[check_in - grace_before, check_out + grace_after]`.

**Common causes:**

- **Timezone mismatch:** The portal uses UTC internally. Verify `check_in` and
  `check_out` include timezone information (e.g., `+00:00` suffix).
- **Stale cache:** Force a poll to refresh the cache:

  ```bash
  curl -s -X POST http://localhost:8080/api/v1/integrations/ha/poll \
    -H "Cookie: session=<admin_session>"
  ```

- **Case sensitivity:** By default, matching is case-insensitive. If you've
  changed `ha_booking_code_case_sensitive: true`, the guest must enter the
  exact case.

---

## Network Connectivity Diagnostics

### Portal Not Reachable from Guest Network

**Diagnostics from a device on the guest VLAN:**

```bash
# Test basic connectivity
ping <portal_ip>

# Test HTTP port
curl -v http://<portal_ip>:8080/api/health

# Test captive portal detection
curl -v http://<portal_ip>:8080/generate_204
```

**Common causes:**

1. **Firewall rules:** The guest VLAN must be able to reach the portal on port
   8080. Check:

   ```bash
   # On the portal host
   iptables -L INPUT -n | grep 8080
   ```

2. **VLAN routing:** Ensure routing exists between the guest VLAN and the
   portal's subnet.

3. **DNS interception:** The Omada controller should redirect DNS and HTTP
   traffic from unauthenticated clients to the portal. Verify the External
   Portal configuration in the Omada controller. See
   [TP-Link Omada Setup](tp_omada_setup.md).

4. **Portal IP in allowed list:** The portal's IP must be in the Omada
   hotspot's pre-authentication access list so guests can reach it before
   being authorized.

### DNS Resolution Issues

**Symptom:** Guest devices cannot resolve the portal hostname.

```bash
# Test DNS from the guest network
nslookup <portal_hostname>
dig <portal_hostname>
```

**Solutions:**

- Use the portal's IP address directly in the Omada External Portal
  configuration instead of a hostname.
- Ensure the DNS server configured for the guest VLAN can resolve the portal
  hostname.
- If using split DNS, verify the portal record exists in the guest-facing zone.

### Post-Authorization Connectivity

**Symptom:** Guest is authorized but some sites don't load.

**Diagnostics:**

```bash
# From the guest device
ping 8.8.8.8          # Test raw connectivity
ping google.com       # Test DNS resolution
curl -I https://google.com  # Test HTTPS
```

**Common causes:**

1. **MTU issues:** Large packets dropped. Test with:

   ```bash
   ping -s 1400 -M do 8.8.8.8
   ```

2. **DNS not working post-auth:** The Omada controller may need to release DNS
   interception after authorization. Check controller DHCP and DNS settings.

3. **Bandwidth limits too restrictive:** Check `upKbps`/`downKbps` in the
   grant configuration.

---

## Database Issues

### Database Locked

**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes attempting concurrent writes to SQLite.

**Solutions:**

1. Ensure only one instance of the captive portal is running:

   ```bash
   ps aux | grep captive
   ```

2. Check for long-running database operations (audit cleanup, grant cleanup).
3. If the database file is on a network filesystem (NFS, CIFS), move it to
   local storage. SQLite does not work reliably over network filesystems.

### Database File Missing or Corrupt

**Symptom:** Application fails to start or returns 500 errors.

**Diagnostics:**

```bash
# Check database file
ls -la /data/captive_portal.db

# Verify database integrity
sqlite3 /data/captive_portal.db "PRAGMA integrity_check;"
```

**Solutions:**

1. If missing, the application should recreate the database on startup. Restart
   the application.
2. If corrupt, restore from backup or delete and restart (all data will be
   lost):

   ```bash
   # Back up the corrupt file first
   cp /data/captive_portal.db /data/captive_portal.db.corrupt
   rm /data/captive_portal.db
   # Restart the application
   ```

3. To change the database location:

   ```yaml
   database_path: /data/captive_portal.db
   ```

### Audit Log Growing Too Large

**Symptom:** Database file size growing rapidly, slow queries.

**Solution:** Configure audit retention (default: 30 days, max: 90 days):

```yaml
audit_retention_days: 14
```

The cleanup service runs automatically. To verify:

```bash
docker logs captive-portal 2>&1 | grep "cleanup"
```

Expected output:

```
INFO: Starting event cleanup (cutoff_date=2025-03-11, retention_days=14)
INFO: Event cleanup completed (deleted_count=1234)
```

---

## Performance Debugging

### High Response Latency

**Diagnostics:**

1. **Check system resources:**

   ```bash
   # CPU and memory usage
   docker stats captive-portal --no-stream

   # Process details
   docker exec captive-portal top -bn1
   ```

2. **Check database performance:**

   ```bash
   # Database file size
   ls -lh /data/captive_portal.db

   # Table row counts
   sqlite3 /data/captive_portal.db "
     SELECT 'grants', COUNT(*) FROM accessgrant
     UNION ALL SELECT 'vouchers', COUNT(*) FROM voucher
     UNION ALL SELECT 'audit_logs', COUNT(*) FROM auditlog
     UNION ALL SELECT 'sessions', COUNT(*) FROM adminsession;
   "
   ```

3. **Check Omada controller latency:**

   ```bash
   # Time a request to the controller
   curl -sk -o /dev/null -w "Connect: %{time_connect}s\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" \
     https://<omada_ip>:8043
   ```

### Slow Guest Authorization

**Possible causes:**

1. **Controller latency:** The authorization flow makes synchronous calls to
   the Omada controller. If the controller is slow, authorization takes longer.
2. **Database contention:** Large audit log or grant tables. Run cleanup:

   ```yaml
   audit_retention_days: 14
   ```

3. **Rate limiter overhead:** Per-IP rate limiting uses in-memory tracking.
   With very high client counts this is usually not an issue, but verify with
   DEBUG logging.

### Memory Usage Growing

**Possible causes:**

1. **Session store not cleaned up:** Expired sessions should be cleaned
   automatically. Check session lifetime configuration:

   ```yaml
   session_lifetime_hours: 24
   ```

2. **Rate limiter state accumulation:** The in-memory rate limiter tracks
   per-IP counters. These expire after the configured window but may
   accumulate under high traffic.

3. **Controller cache:** If the optional cache service is enabled, TTL-based
   cache entries consume memory. Entries expire after 30–60 seconds.

---

## Security and Session Issues

### Session Expired Unexpectedly

**Symptom:** Admin is logged out before the expected session lifetime.

**Possible causes:**

1. Application restarted — sessions are stored in memory and do not survive
   restarts.
2. Session lifetime set too low:

   ```yaml
   session_lifetime_hours: 24  # Range: 1-168 hours
   ```

3. Clock skew between the portal host and the client browser.

### Secure Cookie Not Set

**Symptom:** Cookies not being sent; login appears to succeed but subsequent
requests are unauthenticated.

**Cause:** Cookies are set with `Secure; HttpOnly; SameSite=Lax`. The `Secure`
flag requires HTTPS.

**Solutions:**

1. Use HTTPS in production (reverse proxy with TLS termination).
2. For local development over HTTP, cookies may still work if accessing via
   `localhost` (browsers make exceptions for localhost).
3. Check reverse proxy configuration — it must pass `Set-Cookie` headers
   unmodified.

### Rate Limiter Blocking Legitimate Traffic

**Symptom:** `429 Too Many Requests` from legitimate users.

**Diagnostics:**

Check if multiple users share a single public IP (NAT, VPN, proxy):

```bash
docker logs captive-portal 2>&1 | grep "429\|rate.limit"
```

**Solution:** Increase the rate limit to accommodate shared IPs:

```yaml
rate_limit_attempts: 20
rate_limit_window_seconds: 60
```

If running behind a reverse proxy, ensure trusted proxies are configured so the
portal uses `X-Forwarded-For` for client IP detection instead of the proxy's
IP.

---

## Captive Portal Detection

### Device Not Auto-Redirecting to Portal

**Symptom:** Guest devices connect to WiFi but do not show the captive portal
login page automatically.

**Diagnostics — verify detection endpoints respond correctly:**

```bash
# Android
curl -v http://<portal_ip>:8080/generate_204
# Expected: HTTP 302 redirect to /guest/authorize

# iOS / macOS
curl -v http://<portal_ip>:8080/hotspot-detect.html
# Expected: HTTP 302 redirect to /guest/authorize

# Windows
curl -v http://<portal_ip>:8080/connecttest.txt
# Expected: HTTP 302 redirect to /guest/authorize

# Firefox
curl -v http://<portal_ip>:8080/success.txt
# Expected: HTTP 302 redirect to /guest/authorize
```

**Detection endpoints reference:**

| OS | Endpoint | Method |
|----|----------|--------|
| Android | `/generate_204`, `/gen_204` | GET |
| iOS | `/hotspot-detect.html` | GET |
| macOS | `/hotspot-detect.html`, `/library/test/success.html` | GET |
| Windows | `/connecttest.txt`, `/ncsi.txt` | GET |
| Firefox | `/success.txt` | GET |

**Common causes for detection failure:**

1. **Omada controller not redirecting:** The External Portal URL in the Omada
   hotspot configuration must point to the captive portal's IP and port.
   The controller intercepts HTTP requests from unauthenticated clients and
   redirects them to the portal.

2. **HTTPS probes not intercepted:** Some devices use HTTPS for detection.
   The Omada controller can only intercept HTTP (port 80). Ensure the hotspot
   is configured to intercept HTTP traffic.

3. **Device using cached network state:** The device previously connected and
   cached a "connected" state. Toggle WiFi off and on, or "Forget" the network
   and reconnect.

4. **VPN or DNS-over-HTTPS active:** These bypass captive portal detection.
   The guest must disable VPN/DoH to trigger the detection flow.

---

## FAQ

### Q: How do I reset the admin password?

If you can access the database:

```bash
# Delete all admin accounts (forces re-bootstrap)
sqlite3 /data/captive_portal.db "DELETE FROM adminuser;"
sqlite3 /data/captive_portal.db "DELETE FROM adminsession;"
```

Then bootstrap a new admin account:

```bash
curl -s -X POST http://localhost:8080/api/admin/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "NewSecurePassword123!"}'
```

Alternatively, update the `admin_username` and `admin_password` in the addon
configuration and restart.

### Q: How do I check if the retry queue is processing?

```bash
docker logs captive-portal 2>&1 | grep -i "retry\|enqueue"
```

Look for:

```
INFO: Enqueued authorize for AA:BB:CC:DD:EE:FF, attempt 1/3
INFO: Retry authorize succeeded for AA:BB:CC:DD:EE:FF on attempt 2
```

Or failure:

```
WARNING: Retry authorize failed for AA:BB:CC:DD:EE:FF: Connection refused
ERROR: Max retries (3) exceeded for authorize on AA:BB:CC:DD:EE:FF
```

### Q: Can I run the portal without the Omada controller?

No. The Omada controller is a required dependency — it is the mechanism that
actually grants or revokes WiFi access on the network. Without it, the portal
can accept codes and create grant records, but the guest device will not
receive network access.

### Q: Can I run the portal without Home Assistant?

Yes. Disable the HA poller and use voucher-based authorization only:

```yaml
ha_poller_enabled: false
```

Guests will use admin-generated vouchers to gain access instead of booking
codes.

### Q: How do I revoke all active grants?

From the admin API:

```bash
# List all active grants
GRANTS=$(curl -s http://localhost:8080/api/v1/grants \
  -H "Cookie: session=<admin_session>")

# Revoke each one (extract grant IDs and loop)
echo "$GRANTS" | python3 -c "
import sys, json
grants = json.load(sys.stdin)
for g in grants:
    if g.get('status') == 'active':
        print(g['id'])
" | while read id; do
  curl -s -X POST "http://localhost:8080/api/v1/grants/$id/revoke" \
    -H "Cookie: session=<admin_session>"
done
```

### Q: What happens when the portal restarts?

- **Database state** (grants, vouchers, admin accounts, audit logs) is
  persisted in SQLite and survives restarts.
- **Admin sessions** are stored in memory and will be lost — all admins must
  log in again.
- **Rate limiter state** is stored in memory and resets on restart.
- **HA event cache** is persisted in the database and survives restarts.
- **Retry queue** is lost on restart. Pending retries will not be re-attempted
  automatically. Check the audit log for failed operations.

### Q: How do I back up the portal data?

```bash
# Stop the portal (or use SQLite online backup)
cp /data/captive_portal.db /data/captive_portal.db.backup

# Or use SQLite's built-in backup (safe while running)
sqlite3 /data/captive_portal.db ".backup /data/captive_portal.db.backup"
```

### Q: The portal shows "placeholder" status — what's wrong?

If the root endpoint (`/`) returns:

```json
{
  "name": "Captive Portal Guest Access",
  "status": "placeholder",
  "message": "The full captive portal is not yet wired up."
}
```

This means the addon is running the placeholder entrypoint, not the full
application. The full captive portal application needs to be wired into the
addon entrypoint. Check that the addon build completed successfully and that
the entrypoint script is invoking the correct application module.

### Q: How do I view the OpenAPI documentation?

Log in as an admin and navigate to:

- **Swagger UI:** `http://<portal_ip>:8080/admin/docs`
- **ReDoc:** `http://<portal_ip>:8080/admin/redoc`

These endpoints require admin authentication.

### Q: How do I change the checkout grace period?

```yaml
checkout_grace_minutes: 30   # Range: 0-30 minutes (default: 15)
ha_grace_period_after_hours: 2  # Range: 0+ hours (default: 1)
```

The `checkout_grace_minutes` is the short-term grace after the exact checkout
time. The `ha_grace_period_after_hours` extends the booking window by hours.
Both are additive to the `check_out` timestamp.

---

## Getting Help

If the troubleshooting steps above do not resolve your issue:

1. **Enable DEBUG logging** and reproduce the problem.
2. **Collect relevant logs** using the filtering commands in the
   [Logging and Debug Mode](#logging-and-debug-mode) section.
3. **Check the audit log** for a timeline of events:

   ```bash
   curl -s http://localhost:8080/api/v1/audit/logs \
     -H "Cookie: session=<admin_session>" | python3 -m json.tool
   ```

4. **Review related documentation:**
   - [Architecture Overview](architecture_overview.md) — system design and
     component interactions
   - [HA Integration Guide](ha_integration_guide.md) — Rental Control entity
     setup and configuration
   - [TP-Link Omada Setup](tp_omada_setup.md) — controller configuration and
     hotspot operator accounts
   - [Guest Authorization](guest_authorization.md) — authorization flow details
   - [Permissions Matrix](permissions_matrix.md) — RBAC roles and permissions
