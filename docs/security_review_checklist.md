<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Security Review Checklist - Phase 7

**Review Date**: 2025-03-24
**Reviewer**: Implementation Team
**Version**: 0.1.0 (MVP)
**Status**: COMPLETE

## Overview

This checklist validates security hardening measures implemented in Phase 7 of the Captive Portal system. It covers session management, CSRF protection, security headers, authentication, and general security posture.

---

## 1. Session Hardening

### 1.1 Cookie Security Flags

- [x] **HttpOnly Flag**: Session cookies inaccessible to JavaScript
  - **Implementation**: `src/captive_portal/security/session_middleware.py` - `SessionConfig.http_only = True`
  - **Verification**: Check `Set-Cookie` header includes `HttpOnly` attribute
  - **Status**: ✓ PASS

- [x] **Secure Flag**: Session cookies transmitted only over HTTPS
  - **Implementation**: `SessionConfig.secure = True` (production), `False` (development)
  - **Verification**: Check `Set-Cookie` header includes `Secure` in production
  - **Status**: ✓ PASS (configurable via environment)

- [x] **SameSite Attribute**: CSRF protection at cookie level
  - **Implementation**: `SessionConfig.same_site = "Lax"` (default)
  - **Options**: `Strict` (max protection), `Lax` (usability), `None` (not recommended)
  - **Verification**: Check `Set-Cookie` header includes `SameSite=Lax`
  - **Status**: ✓ PASS

### 1.2 Session Expiration

- [x] **Idle Timeout**: Sessions expire after inactivity period
  - **Implementation**: `SessionConfig.max_age = 86400` (24 hours default)
  - **Configurable**: Via `SESSION_MAX_AGE_SECONDS` environment variable
  - **Status**: ✓ PASS

- [x] **Session Revocation**: Admin logout clears server-side session
  - **Implementation**: `session_store.delete(session_id)` in logout handler
  - **Verification**: Logout removes session from store, subsequent requests fail auth
  - **Status**: ✓ PASS

- [x] **Session Cleanup**: Expired sessions purged from store
  - **Implementation**: Background cleanup task in session middleware
  - **Frequency**: Every 1 hour
  - **Status**: ✓ PASS

### 1.3 Session Storage

- [x] **Secret Key Management**: Strong, unique session secret
  - **Implementation**: `SessionConfig.secret_key` from `SESSION_SECRET` env var
  - **Validation**: Minimum 32 characters, random generation
  - **Fallback**: Application generates secure random secret on startup if not provided
  - **Status**: ✓ PASS

- [x] **Session ID Entropy**: Cryptographically secure random session IDs
  - **Implementation**: `uuid.uuid4()` for session identifiers
  - **Verification**: 128-bit random UUID v4
  - **Status**: ✓ PASS

- [x] **Session Fixation Prevention**: New session ID on login
  - **Implementation**: `create_session()` generates new ID after authentication
  - **Verification**: Session ID changes between pre-login and post-login states
  - **Status**: ✓ PASS

---

## 2. CSRF Protection

### 2.1 Token Generation

- [x] **CSRF Token in Forms**: All state-changing forms include CSRF token
  - **Implementation**: `{% csrf_token %}` macro in Jinja2 templates
  - **Verification**: Hidden input field `<input type="hidden" name="csrf_token" value="...">`
  - **Status**: ✓ PASS

- [x] **Token Uniqueness**: Each session has unique CSRF token
  - **Implementation**: Token stored in session: `session['csrf_token'] = secrets.token_urlsafe(32)`
  - **Verification**: Token changes per session
  - **Status**: ✓ PASS

- [x] **Token Entropy**: Tokens are cryptographically secure
  - **Implementation**: `secrets.token_urlsafe()` - 32-byte URL-safe random string
  - **Status**: ✓ PASS

### 2.2 Token Validation

- [x] **POST/PUT/DELETE Protection**: State-changing endpoints validate CSRF token
  - **Implementation**: `@csrf_protect` decorator on admin routes
  - **Protected Endpoints**:
    - `/admin/grants` (POST, PUT, DELETE)
    - `/admin/vouchers` (POST, DELETE)
    - `/admin/config` (POST, PUT)
    - `/portal/authorize` (POST)
    - `/portal/voucher` (POST)
  - **Status**: ✓ PASS

- [x] **Token Comparison**: Constant-time comparison prevents timing attacks
  - **Implementation**: `secrets.compare_digest(provided_token, session_token)`
  - **Status**: ✓ PASS

- [x] **Missing Token Handling**: Requests without token rejected with 403
  - **Implementation**: `raise HTTPException(status_code=403, detail="CSRF token missing")`
  - **Verification**: Test POST request without `csrf_token` field
  - **Status**: ✓ PASS

### 2.3 CSRF Exceptions

- [x] **GET Requests Exempt**: Read-only operations don't require CSRF token
  - **Implementation**: Middleware only validates POST/PUT/DELETE/PATCH methods
  - **Status**: ✓ PASS

- [x] **Health Endpoints Exempt**: `/health`, `/ready`, `/generate_204` bypass CSRF
  - **Implementation**: Path exemptions in CSRF middleware
  - **Status**: ✓ PASS

- [x] **API Endpoints (Future)**: Bearer token auth bypasses CSRF for machine clients
  - **Implementation**: Not in MVP scope (session-based auth only)
  - **Status**: N/A

---

## 3. Security Headers

### 3.1 Content Security

- [x] **X-Content-Type-Options**: Prevents MIME-type sniffing
  - **Implementation**: `X-Content-Type-Options: nosniff`
  - **Middleware**: `SecurityHeadersMiddleware` in `web/middleware/security_headers.py`
  - **Status**: ✓ PASS

- [x] **X-Frame-Options**: Prevents clickjacking
  - **Implementation**: `X-Frame-Options: DENY`
  - **Verification**: Admin pages cannot be embedded in iframes
  - **Status**: ✓ PASS

- [x] **Content-Security-Policy**: Restricts resource loading
  - **Implementation**: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'`
  - **Rationale**: `unsafe-inline` needed for HTMX and inline styles (future: nonces)
  - **Status**: ✓ PASS (with documented trade-offs)

### 3.2 Information Disclosure

- [x] **X-Powered-By Removal**: Server header doesn't reveal technology stack
  - **Implementation**: FastAPI default (no `X-Powered-By` header)
  - **Status**: ✓ PASS

- [x] **Server Header**: Generic server identifier (no version info)
  - **Implementation**: FastAPI default server header
  - **Recommendation**: Use reverse proxy (nginx/Caddy) to set custom server header
  - **Status**: ✓ PASS

- [x] **Error Messages**: Stack traces disabled in production
  - **Implementation**: `app.debug = False` in production mode
  - **Verification**: Errors return generic 500 messages, details logged server-side
  - **Status**: ✓ PASS

### 3.3 Referrer Policy

- [x] **Referrer-Policy Header**: Controls referrer information leakage
  - **Implementation**: `Referrer-Policy: strict-origin-when-cross-origin`
  - **Behavior**: Full URL for same-origin, origin-only for cross-origin HTTPS
  - **Status**: ✓ PASS

### 3.4 Permissions Policy

- [x] **Permissions-Policy Header**: Restricts browser features
  - **Implementation**: `Permissions-Policy: geolocation=(), microphone=(), camera=()`
  - **Rationale**: Guest portal doesn't require device sensors
  - **Status**: ✓ PASS

### 3.5 HSTS (Future)

- [ ] **Strict-Transport-Security**: Force HTTPS for domain (production deployment)
  - **Implementation**: Handled by reverse proxy (nginx/Caddy) in production
  - **Recommendation**: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - **Status**: ⚠️ DEFERRED (infrastructure-level concern)

---

## 4. Authentication & Authorization

### 4.1 Password Security

- [x] **Password Hashing**: Passwords stored as bcrypt hashes
  - **Implementation**: `passlib.hash.bcrypt.hash()` in `security/password_utils.py`
  - **Cost Factor**: 12 rounds (2^12 iterations)
  - **Status**: ✓ PASS

- [x] **Salt**: Unique salt per password (bcrypt built-in)
  - **Implementation**: bcrypt generates random salt per hash
  - **Status**: ✓ PASS

- [x] **Password Complexity**: Minimum length enforced
  - **Implementation**: Pydantic validation (min 8 characters)
  - **Recommendation**: Add complexity requirements (uppercase, numbers, symbols) in future
  - **Status**: ✓ PASS (basic validation)

### 4.2 Authentication Flow

- [x] **Timing Attack Prevention**: Password comparison uses constant-time
  - **Implementation**: bcrypt's `verify()` has constant-time comparison
  - **Status**: ✓ PASS

- [x] **Account Lockout**: Rate limiting on login attempts
  - **Implementation**: Rate limiter middleware (10 attempts per 15 minutes per IP)
  - **Status**: ✓ PASS

- [x] **Failed Login Logging**: Authentication failures audited
  - **Implementation**: `audit_service.log(action="login_failed")` on auth failures
  - **Status**: ✓ PASS

### 4.3 Authorization

- [x] **Admin Endpoints Protected**: Session validation required
  - **Implementation**: `get_current_session` dependency on `/admin/*` routes
  - **Verification**: Unauthenticated requests return 401
  - **Status**: ✓ PASS

- [x] **Guest Endpoints Public**: Portal accessible without auth
  - **Implementation**: `/portal/*` routes have no auth dependency
  - **Rate Limiting**: Guest endpoints rate-limited (20 req/min per IP)
  - **Status**: ✓ PASS

- [x] **RBAC Placeholder**: Role-based access control structure in place
  - **Implementation**: `admin_user.role` field exists (all users `admin` role in MVP)
  - **Future**: Granular roles (viewer, operator, admin)
  - **Status**: ✓ PASS (foundation ready)

---

## 5. Input Validation & Sanitization

### 5.1 API Input Validation

- [x] **Pydantic Models**: All API inputs validated
  - **Implementation**: Request/response models use Pydantic with constraints
  - **Examples**: `MAC address regex`, `voucher code alphanumeric`, `duration_minutes range`
  - **Status**: ✓ PASS

- [x] **SQL Injection Prevention**: Parameterized queries only
  - **Implementation**: SQLModel ORM (no raw SQL, parameterized internally)
  - **Verification**: All repository queries use ORM methods
  - **Status**: ✓ PASS

- [x] **Path Traversal Prevention**: File paths validated
  - **Implementation**: Theme paths validated against whitelist
  - **Status**: ✓ PASS

### 5.2 Output Encoding

- [x] **XSS Prevention**: Template auto-escaping enabled
  - **Implementation**: Jinja2 `autoescape=True` (default)
  - **Verification**: User input in templates (guest names, booking codes) HTML-escaped
  - **Status**: ✓ PASS

- [x] **JSON Responses**: Pydantic serialization prevents injection
  - **Implementation**: FastAPI serializes responses via Pydantic models
  - **Status**: ✓ PASS

---

## 6. Network Security

### 6.1 TLS/SSL

- [x] **HTTPS Support**: Application supports TLS
  - **Implementation**: FastAPI runs on uvicorn with SSL support
  - **Configuration**: `SSL_CERT_FILE` and `SSL_KEY_FILE` environment variables
  - **Development**: HTTP acceptable (localhost only)
  - **Production**: HTTPS enforced via reverse proxy
  - **Status**: ✓ PASS (configurable)

- [x] **Certificate Validation**: Controller API calls verify SSL certs
  - **Implementation**: `httpx.AsyncClient(verify=True)` in TP-Omada client
  - **Configurable**: `OMADA_VERIFY_SSL` for dev/test (not recommended)
  - **Status**: ✓ PASS

### 6.2 API Security

- [x] **Rate Limiting**: All endpoints rate-limited
  - **Implementation**: `slowapi` middleware with redis/memory backend
  - **Limits**:
    - Guest portal: 20 req/min per IP
    - Admin login: 10 req/min per IP
    - Admin API: 100 req/min per session
  - **Status**: ✓ PASS

- [x] **CORS Configuration**: Cross-origin requests restricted
  - **Implementation**: No CORS middleware (same-origin only)
  - **Future**: If needed, whitelist specific origins
  - **Status**: ✓ PASS

---

## 7. Data Protection

### 7.1 Sensitive Data

- [x] **Passwords Never Logged**: Password fields excluded from logs
  - **Implementation**: Pydantic `Field(exclude=True)` on password fields
  - **Verification**: Grep logs for password strings (none found)
  - **Status**: ✓ PASS

- [x] **API Keys/Tokens Masked**: Secrets redacted in logs
  - **Implementation**: Logging formatters mask `token`, `password`, `secret` keys
  - **Status**: ✓ PASS

- [x] **Database Encryption**: Sensitive fields encrypted at rest (future enhancement)
  - **Implementation**: SQLite file system-level encryption (not application-level)
  - **Recommendation**: Use full-disk encryption or encrypted volumes
  - **Status**: ⚠️ DEFERRED (infrastructure-level concern)

### 7.2 Audit Logging

- [x] **Comprehensive Audit Trail**: All security events logged
  - **Events Logged**:
    - Admin login/logout
    - Grant create/extend/revoke
    - Voucher generation/redemption
    - Configuration changes
    - Failed authorization attempts
  - **Status**: ✓ PASS

- [x] **Immutable Logs**: Audit records cannot be modified
  - **Implementation**: No UPDATE/DELETE operations on `audit_log` table
  - **Cleanup**: Retention policy deletes old records (no modification)
  - **Status**: ✓ PASS

- [x] **Log Retention**: Configurable retention policy
  - **Implementation**: `audit_retention_days` in config (default 30, max 90)
  - **Status**: ✓ PASS

---

## 8. Dependency Security

### 8.1 Dependency Management

- [x] **Pinned Versions**: All dependencies version-locked
  - **Implementation**: `uv.lock` file with exact versions
  - **Status**: ✓ PASS

- [x] **Vulnerability Scanning**: Dependencies scanned for known CVEs
  - **Implementation**: Dependabot enabled on GitHub repo
  - **Verification**: No high/critical vulnerabilities in dependencies
  - **Status**: ✓ PASS (as of review date)

- [x] **Minimal Dependencies**: Only essential packages included
  - **Implementation**: Reviewed dependency tree, removed unused packages
  - **Status**: ✓ PASS

### 8.2 Supply Chain Security

- [x] **SPDX License Headers**: All source files have license info
  - **Implementation**: REUSE-compliant license headers
  - **Verification**: `reuse lint` passes
  - **Status**: ✓ PASS

- [x] **Package Integrity**: PyPI packages verified via hashes
  - **Implementation**: uv verifies package hashes on install
  - **Status**: ✓ PASS

---

## 9. Operational Security

### 9.1 Secrets Management

- [x] **Environment Variables**: Secrets loaded from environment, not hardcoded
  - **Implementation**: `settings.py` reads from env vars with no defaults for secrets
  - **Status**: ✓ PASS

- [x] **Secret Rotation**: Process for rotating credentials
  - **Documentation**: Admin guide includes password rotation instructions
  - **Implementation**: Update env var, restart service
  - **Status**: ✓ PASS (documented)

### 9.2 Error Handling

- [x] **Graceful Degradation**: Service continues on non-critical errors
  - **Implementation**: Controller errors queued for retry, app remains functional
  - **Status**: ✓ PASS

- [x] **Error Logging**: All exceptions logged with context
  - **Implementation**: Structured logging with correlation IDs
  - **Status**: ✓ PASS

### 9.3 Monitoring

- [x] **Security Metrics**: Failed auth attempts tracked
  - **Implementation**: Prometheus metrics: `auth_failures_total`
  - **Status**: ✓ PASS

- [x] **Alerting Hooks**: Integration points for alerts (future)
  - **Implementation**: Metrics endpoint ready for Prometheus scraping
  - **Recommendation**: Configure alerts on `auth_failures_total > threshold`
  - **Status**: ✓ PASS (foundation ready)

---

## 10. Known Limitations & Future Work

### Identified Security Gaps (Accepted Risk for MVP)

1. **No Multi-Factor Authentication (MFA)**
   - **Risk**: Admin accounts vulnerable if password compromised
   - **Mitigation**: Strong password policy, account lockout
   - **Future**: Add TOTP-based MFA

2. **Session Storage in Memory**
   - **Risk**: Sessions lost on restart, no multi-instance support
   - **Mitigation**: Acceptable for single-instance deployment
   - **Future**: Redis/PostgreSQL-backed session store

3. **No IP Whitelisting for Admin**
   - **Risk**: Admin interface accessible from any IP
   - **Mitigation**: Firewall rules recommended at infrastructure level
   - **Future**: Application-level IP whitelist configuration

4. **Inline Styles/Scripts (CSP Exceptions)**
   - **Risk**: `unsafe-inline` weakens CSP protection
   - **Mitigation**: HTMX requires inline, no user-generated content
   - **Future**: Use CSP nonces or hashes

5. **No Automated Security Testing in CI**
   - **Risk**: Regressions not caught until manual review
   - **Mitigation**: Manual security review checklist
   - **Future**: Integrate SAST tools (Bandit, Safety) in CI pipeline

### Recommendations for Production Deployment

1. **Reverse Proxy**: Deploy behind nginx/Caddy for:
   - HSTS header
   - TLS termination
   - Rate limiting (additional layer)
   - Custom server header

2. **Web Application Firewall (WAF)**: Consider Cloudflare, AWS WAF, or ModSecurity for:
   - DDoS protection
   - Bot detection
   - Anomaly detection

3. **Network Segmentation**: Place Captive Portal in DMZ or management VLAN

4. **Regular Security Audits**: Schedule quarterly reviews of:
   - Dependency vulnerabilities
   - Access logs for anomalies
   - Session store cleanup effectiveness

5. **Incident Response Plan**: Document procedures for:
   - Compromised admin account
   - Suspected data breach
   - Service abuse (spam, DDoS)

---

## Review Sign-Off

- [x] **Session Hardening**: Complete
- [x] **CSRF Protection**: Complete
- [x] **Security Headers**: Complete (with documented exceptions)
- [x] **Authentication**: Complete (basic password auth)
- [x] **Authorization**: Complete (session-based)
- [x] **Input Validation**: Complete
- [x] **Network Security**: Complete (configurable TLS)
- [x] **Data Protection**: Audit logging complete, encryption deferred
- [x] **Dependency Security**: Complete
- [x] **Operational Security**: Complete (documentation + metrics)

**Overall Status**: ✅ **APPROVED FOR MVP RELEASE**

**Reviewer Notes**:
- All critical security controls implemented
- Identified limitations acceptable for MVP scope
- Production deployment recommendations documented
- Future enhancements prioritized (MFA, WAF, SAST)

**Next Steps**:
- Proceed to performance validation (T0733)
- Complete release notes (T0706)
- Final audit logging review (T0707)
