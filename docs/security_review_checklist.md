<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Security Review Checklist — Captive Portal MVP

This checklist documents the security controls implemented in the captive
portal add-on together with notes for reviewers. Each section references
the concrete source files that implement the control.

---

## 1. Session Hardening

**Implementation:** `src/captive_portal/security/session_middleware.py`

| Control | Value | Notes |
|---------|-------|-------|
| Cookie `Secure` flag | `True` | Cookies only sent over HTTPS |
| Cookie `HttpOnly` flag | `True` | Prevents JavaScript access |
| Cookie `SameSite` | `strict` | Strict cross-origin protection for admin sessions |
| Session ID entropy | `secrets.token_urlsafe(32)` | 256-bit cryptographic random |
| Idle timeout | 30 minutes | Configurable via `SessionConfig.idle_minutes` (D17) |
| Absolute timeout | 8 hours | Configurable via `SessionConfig.max_hours` (D17) |
| Session store | In-memory `SessionStore` | Sessions are not persisted across restarts |
| IP / User-Agent tracking | Stored per session | Enables anomaly detection in audit logs |
| Expired session cleanup | Automatic | `SessionStore` prunes expired entries |

**Review items:**

- [x] `set_cookie()` applies Secure, HttpOnly, SameSite flags
      (`session_middleware.py` lines 156-163)
- [x] Session IDs generated with `secrets.token_urlsafe(32)`
      (`session_middleware.py` line 63)
- [x] Both idle and absolute timeout enforced on every request
      (`session_middleware.py` lines 125-139)
- [ ] Session ID rotation on privilege escalation — not currently
      implemented; consider adding after login success

---

## 2. CSRF Protection

**Implementation:** `src/captive_portal/security/csrf.py`

| Control | Value |
|---------|-------|
| Pattern | Double-submit cookie |
| Token entropy | `secrets.token_urlsafe(32)` |
| Comparison | `secrets.compare_digest()` (constant-time) |
| Header name | `X-CSRF-Token` |
| Form field fallback | Supported |
| Admin cookie `SameSite` | `strict` |
| Guest cookie `SameSite` | `lax` |
| Cookie `HttpOnly` | `False` (required so JavaScript can read the token) |

**Callers:**

| Route | File | Purpose |
|-------|------|---------|
| Admin modification endpoints | `api/routes/admin_accounts.py` line 116 | Validates before account changes |
| Guest authorize | `api/routes/guest_portal.py` line 259 | Validates before granting access |
| Bootstrap CSRF endpoint | `api/routes/admin_auth.py` lines 202-219 | Issues CSRF token |

**Review items:**

- [x] Token generated with CSPRNG
- [x] Constant-time comparison prevents timing attacks
- [x] Token validated on all state-changing endpoints
- [x] Separate SameSite policies for admin (`strict`) and guest (`lax`)

---

## 3. Security Headers

**Implementation:** `src/captive_portal/web/middleware/security_headers.py`
Registered in `app.py` line 70.

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'` | XSS / injection mitigation |
| `X-Frame-Options` | `DENY` | Clickjacking prevention |
| `X-Content-Type-Options` | `nosniff` | MIME-sniffing prevention |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS filter |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Prevents referrer leakage |
| `Permissions-Policy` | Disables geolocation, microphone, camera, payment, USB, magnetometer, gyroscope, accelerometer | Feature restriction |

**Guest portal CSP** (`guest_portal.py` lines 111-120):

- Allows `'unsafe-inline'` for styles (template rendering)
- Scripts restricted to `'self'`
- `frame-ancestors 'none'`

**Review items:**

- [x] Middleware registered before route handlers
- [x] CSP includes `frame-ancestors 'none'` (supplements X-Frame-Options)
- [x] No `'unsafe-eval'` anywhere
- [ ] Consider removing `'unsafe-inline'` from guest style-src by using
      external CSS

---

## 4. Authentication

### 4.1 Admin Authentication

**Implementation:** `src/captive_portal/api/routes/admin_auth.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/auth/login` | POST | Validate credentials, create session |
| `/api/admin/auth/logout` | POST | Destroy session, clear cookies |
| `/api/admin/auth/bootstrap` | POST | First-run admin creation (one-time) |

- Login sets session cookie + CSRF cookie on success
- Failed login returns 401 with generic message (no user enumeration)
- Bootstrap returns 409 if an admin already exists

### 4.2 Password Hashing

**Implementation:** `src/captive_portal/security/password_hashing.py`

| Parameter | Value |
|-----------|-------|
| Algorithm | Argon2id |
| Time cost | 3 iterations |
| Memory cost | 64 MiB |
| Parallelism | 4 threads |
| Hash length | 32 bytes |
| Salt length | 16 bytes |
| Format | PHC string |

Parameters follow OWASP recommendations for Argon2id.

**Callers:** `admin_auth.py` (login, bootstrap), `admin_accounts.py`
(account create, password update).

### 4.3 Session Management

**Implementation:** `src/captive_portal/security/session_middleware.py`

- `get_current_admin()` dependency in `admin_accounts.py` (lines 54-75)
  validates session and retrieves admin from database
- All admin routes require this dependency
- Returns 401 when session is missing or expired

### 4.4 RBAC

**Implementation:** `src/captive_portal/security/rbac.py`

Roles: `viewer`, `auditor`, `operator`, `admin`. Deny-by-default
permission matrix. Returns 403 on unauthorized access (FR-017).

**Review items:**

- [x] Password hashing uses Argon2id with OWASP parameters
- [x] No plaintext passwords stored
- [x] Session cookies are HTTP-only
- [x] Bootstrap endpoint is one-shot
- [x] RBAC deny-by-default

---

## 5. Input Validation & SQL Injection Prevention

### 5.1 Pydantic / SQLModel Validation

All request payloads are validated via Pydantic models before reaching
business logic:

| Model | File | Key constraints |
|-------|------|-----------------|
| `LoginRequest` | `admin_auth.py` | Username + password required |
| `BootstrapRequest` | `admin_auth.py` | Email validated with `EmailStr` |
| `AdminUser` | `models/admin_user.py` | `max_length=64` (username), `max_length=255` (email) |
| `Voucher` | `models/voucher.py` | A-Z0-9 codes, configurable 4-24 chars (FR-018) |
| `AuditLog` | `models/audit_log.py` | Field-level `max_length` constraints |
| `PortalConfig` | `models/portal_config.py` | `Field(ge=1, le=1000)` for rate limits |

### 5.2 Parameterized Queries

All database access uses SQLModel/SQLAlchemy ORM with parameterized
statements via the repository abstraction layer
(`persistence/repositories.py`).

Example:

```python
select(Voucher).where(Voucher.booking_ref == booking_ref)
```

No raw SQL string concatenation with user input exists in the codebase. Only a static `SELECT 1` is used for readiness health checks. Foreign key
constraints are enabled in `persistence/database.py` (line 50).

### 5.3 Output Encoding

- Jinja2 auto-escaping enabled explicitly (`guest_portal.py` line 36)
- Additional output sanitisation with regex (`guest_portal.py` line 150)

**Review items:**

- [x] No raw SQL involving user input; only `SELECT 1` for health checks
- [x] All user input validated before use
- [x] Jinja2 auto-escaping enabled
- [x] Foreign key constraints enabled

---

## 6. Rate Limiting

**Implementation:** `src/captive_portal/security/rate_limiter.py`

| Parameter | Default | Config Source |
|-----------|---------|---------------|
| Max attempts | 5 | `PortalConfig.rate_limit_attempts` |
| Window | 60 seconds | `PortalConfig.rate_limit_window_seconds` |
| Scope | Per IP | Rolling window |
| Cleanup interval | 5 minutes | Automatic (prevents memory leak) |

**Behaviour:**

- `is_allowed(ip)` returns `False` when limit exceeded
- Returns HTTP 429 with `Retry-After` header (`guest_portal.py` line 284)
- Cleared on successful authorization (`guest_portal.py` line 521)
- Rate limit violations are audited with outcome `rate_limited`

**Review items:**

- [x] Rate limiter applied to guest authorization endpoint
- [x] 429 response includes `Retry-After` header
- [x] Audit logging on rate limit trigger
- [ ] Consider adding rate limiting to admin login endpoint
- [ ] Consider distributed rate limiting if multiple instances are
      deployed

---

## 7. HTTPS / TLS Requirements

**Current status:** TLS is handled at the deployment layer, not in the
application.

| Layer | Detail |
|-------|--------|
| Application | Runs on port 8080 (HTTP) |
| Deployment | Expected behind Home Assistant Ingress reverse proxy with TLS |
| Guest portal | `cookie_secure=False` for captive portal HTTP mode (`guest_portal.py` line 42) |
| Upstream connections | `verify_ssl=True` by default for Omada controller (`controllers/tp_omada/base_client.py`) |

**Redirect validation:** `services/redirect_validator.py` restricts
protocols to HTTP/HTTPS only, preventing open redirect attacks.

**Review items:**

- [x] Upstream (Omada) connections verify SSL certificates
- [x] Redirect validator prevents protocol injection
- [ ] Document TLS termination requirements in deployment guide
- [ ] Consider `TrustedHostMiddleware` for HTTPS enforcement

---

## 8. Audit Logging Coverage

**Implementation:** `src/captive_portal/services/audit_service.py`
**Model:** `src/captive_portal/models/audit_log.py`

### 8.1 Audit Entry Fields

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Immutable primary key |
| `actor` | str (128) | Username, `system`, or `guest:{mac}` |
| `role_snapshot` | str (32) | Actor's role at time of action |
| `action` | str (64) | Dot-notation action (e.g., `voucher.create`) |
| `target_type` | str (32) | Entity type (`voucher`, `grant`, `session`) |
| `target_id` | str (128) | Entity identifier |
| `timestamp_utc` | datetime | Immutable UTC timestamp (indexed) |
| `outcome` | str (32) | `success`, `failure`, `denied`, `error`, `rate_limited` |
| `meta` | JSON | IP address, user-agent, error details, reason |

### 8.2 Audited Actions

| Action | Outcome(s) | File |
|--------|------------|------|
| `admin.login` | success, failure | `admin_auth.py` |
| `guest.authorize` | success, denied, error, rate_limited | `guest_portal.py` |
| `create_voucher` | success | `vouchers.py` |
| `extend_grant` | success | `grants.py` |
| `revoke_grant` | success | `grants.py` |
| `list_grants` | success | `grants.py` |
| `create_integration` | success | `integrations.py`, `integrations_ui.py` |
| `update_integration` | success | `integrations_ui.py` |
| `delete_integration` | success | `integrations_ui.py` |
| `portal_config.update` | success | `portal_settings_ui.py` |
| `event.cleanup` | success | `cleanup_service.py` |

### 8.3 Known Gaps

See `docs/audit_logging_review.md` for the full gap analysis. Key
missing items:

- Admin logout not audited
- Admin bootstrap not audited
- Admin account create / update / delete not audited
- RBAC denials not consistently audited
- Booking authorization flow not audited

**Review items:**

- [x] All successful guest authorizations logged
- [x] All failed guest authorizations logged with reason
- [x] Rate limit violations logged
- [x] Admin login success and failure logged
- [ ] Fill audit gaps identified in `docs/audit_logging_review.md`

---

## Reviewer Sign-off

| Reviewer | Date | Result |
|----------|------|--------|
| ___________ | __________ | ☐ Pass ☐ Fail |
| ___________ | __________ | ☐ Pass ☐ Fail |
