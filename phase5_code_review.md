<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Phase 5 Code Review: Guest Portal & Authentication

**Review Date**: 2025-10-30
**Branch**: phase3 (containing Phase 5 work)
**Reviewer**: AI Code Review
**Total Commits**: 13
**Files Changed**: 43
**Lines Added**: ~2,945

---

## Executive Summary

Phase 5 implementation introduces the guest-facing captive portal with booking code and voucher authentication, rate limiting, and redirect handling. The code is generally well-structured with good test coverage (202 passing tests), proper documentation, and security considerations. However, there are several critical and high-priority issues that should be addressed before merging to main.

**Overall Status**: ⚠️ CONDITIONAL APPROVAL - Critical issues must be resolved

**Pre-commit Status**: ✅ PASSING (all checks pass)
**Test Status**: ✅ PASSING (202 passed, 132 skipped)
**MyPy Status**: ✅ PASSING (no errors)

---

## Critical Issues (Must Fix Before Merge)

### C1: Incomplete Implementation - TODO Comments in Production Code ✅ RESOLVED
**Severity**: 🔴 CRITICAL
**File**: `src/captive_portal/api/routes/guest_portal.py`
**Lines**: 87-89, 102
**Status**: ✅ FIXED in commit 2d7002f

**Issue**:
```python
# TODO: Process validated code and create access grant
# For now, just validate the code type
_ = validation_result  # Used for future grant creation

# TODO: Set authorization cookie/header for controller integration
```

**Problem**: The guest authorization flow validates codes but doesn't actually create access grants or authorize clients on the controller. This means the feature is non-functional - guests cannot actually get network access.

**Impact**: Phase 5 deliverables are incomplete. The guest portal appears to work but provides no actual network authorization.

**Resolution**:
- ✅ Implemented complete grant creation for both voucher and booking code paths
- ✅ Added MAC address extraction from request headers (X-MAC-Address, X-Client-Mac, Client-MAC)
- ✅ Integrated VoucherService for voucher redemption
- ✅ Integrated BookingCodeValidator with time window enforcement
- ✅ Added booking grace period support (60 min early check-in, configurable checkout)
- ✅ Create AccessGrant records with PENDING status
- ✅ Implemented duplicate grant detection for bookings
- ✅ Set grant_id cookie for controller integration
- ✅ Added comprehensive error handling for all validation paths
- ✅ Store case-sensitive booking identifiers for admin cross-reference

**Required for**: MVP/Phase 5 completion

---

### C2: Insecure Client IP Detection ✅ RESOLVED
**Severity**: 🔴 CRITICAL
**File**: `src/captive_portal/api/routes/guest_portal.py`
**Lines**: 67
**Status**: ✅ FIXED in commit 4836586

**Issue**:
```python
client_ip = request.client.host if request.client else "unknown"
```

**Problem**: Trusts `request.client.host` which can be spoofed via proxy headers. Rate limiting can be easily bypassed by manipulating `X-Forwarded-For` headers.

**Impact**:
- Rate limiting is ineffective against determined attackers
- Brute-force attacks on booking codes/vouchers are possible
- Security control is trivially bypassed

**Resolution**:
- ✅ Created `get_client_ip()` utility function in `src/captive_portal/utils/network_utils.py`
- ✅ Implements proper proxy header validation with trusted network checking
- ✅ Supports X-Forwarded-For and X-Real-IP headers
- ✅ Only trusts proxy headers from configured trusted networks (private IPs by default)
- ✅ Takes leftmost IP from X-Forwarded-For chain (original client)
- ✅ Falls back to direct connection IP if headers are invalid or untrusted
- ✅ Handles IPv4 and IPv6 addresses
- ✅ Added comprehensive test suite (13 tests covering all scenarios)
- ✅ Updated guest portal to use the new utility with private network trust

**Required for**: Security compliance

---

### C3: Missing CSRF Protection on Guest Forms ✅ RESOLVED
**Severity**: 🔴 CRITICAL
**File**: `src/captive_portal/api/routes/guest_portal.py`
**Lines**: 42-103
**Status**: ✅ FIXED in commit [pending]

**Issue**: The POST `/guest/authorize` endpoint accepts form submissions without CSRF protection.

**Problem**: While CSRF protection exists for admin routes (`csrf.py`), guest authorization forms lack CSRF tokens. This allows malicious sites to submit authorization requests on behalf of users.

**Attack Scenario**:
1. Attacker creates malicious website
2. User visits malicious site while on the network
3. Site submits hidden form to `/guest/authorize` with attacker's code
4. Attacker's code is validated using victim's IP/session

**Impact**:
- Account/code enumeration attacks
- Unauthorized code redemption
- Rate limit exhaustion for legitimate users

**Resolution**:
- ✅ Created guest-specific CSRF configuration with lighter-weight settings
- ✅ Set cookie_secure=False to support HTTP captive portal environments
- ✅ Set cookie_samesite="lax" for redirect scenarios
- ✅ Updated GET /guest/authorize to generate and set CSRF token in cookie
- ✅ Updated authorize.html template to include CSRF token in form
- ✅ Updated POST /guest/authorize to validate CSRF token before processing
- ✅ Updated integration tests to extract and include CSRF tokens
- ✅ Fixed missing device_id in booking code grant creation

**Required for**: Security compliance

---

## High Priority Issues (Should Fix Before Merge)

### H1: Rate Limiter Memory Leak Risk ✅ RESOLVED
**Severity**: 🟠 HIGH
**File**: `src/captive_portal/security/rate_limiter.py`
**Lines**: 33, 80-88
**Status**: ✅ FIXED in commit 138df3f

**Issue**:
```python
self._attempts: dict[str, list[datetime]] = defaultdict(list)

def cleanup(self) -> None:
    """Remove expired entries to free memory."""
    # Manual cleanup method exists but may not be called regularly
```

**Problem**: The rate limiter stores all IP addresses indefinitely in memory. The `cleanup()` method exists but there's no evidence of it being called periodically.

**Impact**:
- Memory consumption grows unbounded over time
- In a busy network, thousands of guest IPs accumulate
- Potential DoS via memory exhaustion
- Memory leak in long-running processes

**Resolution**:
- ✅ Implemented automatic lazy cleanup in `is_allowed()` method
- ✅ Cleanup runs every 5 minutes (configurable via `_cleanup_interval_seconds`)
- ✅ Tracks last cleanup time with `_last_cleanup` timestamp
- ✅ Removes expired entries for all IPs during periodic cleanup
- ✅ Updated class and method docstrings to document automatic behavior
- ✅ Added comprehensive test for automatic cleanup functionality
- ✅ All existing tests continue to pass

**Required for**: Production readiness

---

### H2: No MAC Address Validation or Storage ✅ RESOLVED
**Severity**: 🟠 HIGH
**File**: Multiple (missing functionality)
**Lines**: N/A
**Status**: ✅ FIXED in commit [pending]

**Issue**: The system doesn't capture or validate client MAC addresses during authorization.

**Problem**:
- Access grants are created but not tied to specific devices
- No way to authorize client MAC on controller
- Controller integration will fail (requires MAC address)
- Guests could share codes across unlimited devices

**Impact**:
- Phase 5 deliverable incomplete (can't actually grant network access)
- Security issue: one code could authorize entire household/group
- Controller API calls will fail without MAC addresses

**Resolution**:
- ✅ Created `validate_mac_address()` utility function in `src/captive_portal/utils/network_utils.py`
- ✅ Validates MAC address format (6 octets, 12 hex characters)
- ✅ Accepts multiple common formats (colon, hyphen, dot-separated, unseparated)
- ✅ Normalizes to uppercase colon-separated format (AA:BB:CC:DD:EE:FF)
- ✅ Updated `_extract_mac_address()` in guest portal to validate extracted MAC
- ✅ Provides clear error messages for invalid MAC formats
- ✅ Added comprehensive test suite (19 tests covering all format variations)
- ✅ MAC addresses are already stored in `AccessGrant.mac` field by grant creation logic

**Required for**: Phase 5 completion

---

### H3: Booking Code Window Logic Missing
**Severity**: 🟠 HIGH
**File**: `src/captive_portal/services/booking_code_validator.py`
**Lines**: 95-185
**Status**: ✅ FIXED in commit 3cdfe11

**Issue**: Validator has helper methods (`is_within_checkin_window`, `get_checkin_window_minutes`, etc.) but they're not integrated into the authorization flow.

**Problem**:
- Booking codes are validated but check-in/checkout windows are not enforced
- Guests could access network days before arrival or after departure
- Grace periods defined but not applied

**Specification Requirement**: "Events 0 and 1 are always the most relevant events as event 0 is the current booking or booking that is checking out on 'today' with event 1 being the incoming guest"

**Impact**:
- Security: unauthorized access outside booking dates
- Business logic: contradicts rental control integration specification
- Guest experience: confusion when codes work at wrong times

**Resolution**:
- ✅ Explicitly enabled Jinja2 auto-escaping for XSS protection
- ✅ Added comprehensive security headers to all guest portal responses:
  - Content-Security-Policy (prevents XSS, inline script injection)
  - X-Frame-Options: DENY (prevents clickjacking)
  - X-Content-Type-Options: nosniff (prevents MIME-sniffing)
  - Referrer-Policy: strict-origin-when-cross-origin
- ✅ Implemented _add_security_headers() helper for consistent header application
- ✅ Implemented _sanitize_error_message() to strip HTML tags from user input
- ✅ Limited error message length to 500 characters
- ✅ Registered guest routes in test fixture (conftest.py)
- ✅ Added comprehensive test suite (10 integration tests):
  - Security headers verification on all guest pages
  - XSS payload sanitization (script tags, img tags)
  - HTML entity escaping verification
  - Error message truncation
  - Jinja2 auto-escape validation
  - Inline script detection

**Required for**: Business logic correctness

---

### H4: Case-Sensitive Storage Not Implemented ✅ RESOLVED
**Severity**: 🟠 HIGH
**File**: `src/captive_portal/services/booking_code_validator.py`
**Lines**: 57-93
**Status**: ✅ FIXED in commit [pending]

**Issue**: Documentation states "case-sensitive storage" but implementation only stores what HA provides.

**Problem**:
- Booking codes are matched case-insensitively (correct) ✅
- But nowhere do we store the original user input with case preserved
- AccessGrant records don't capture the original booking identifier as entered

**Specification**: "Booking identifiers shall be case sensitive as the admin may need to cross reference data in the system with bookings."

**Impact**:
- Admin cannot cross-reference bookings with original case
- Audit logs lack original user input
- Potential mismatch with external booking systems

**Resolution**:
- ✅ Added `user_input_code` field to AccessGrant model to store original user input with case preserved
- ✅ Updated guest portal to populate `user_input_code` from `validation_result.original_code`
- ✅ `booking_ref` continues to store the case-sensitive HA identifier (slot_code or slot_name)
- ✅ `integration_id` field already tracks which integration was used for authorization
- ✅ Admin can now cross-reference both user input and system booking identifiers

**Required for**: Audit compliance and admin usability

---

## Medium Priority Issues (Should Address)

### M1: Redirect Validation Too Permissive ✅ RESOLVED
**Severity**: 🟡 MEDIUM
**File**: `src/captive_portal/services/redirect_validator.py`
**Lines**: 30-71
**Status**: ✅ FIXED in commit 5f47e13

**Issue**:
```python
# Allow relative URLs (no scheme or netloc)
if not parsed.scheme and not parsed.netloc:
    return True
```

**Problem**: All relative URLs are allowed, including:
- `//evil.com/phishing` (protocol-relative URL)
- `///etc/passwd` (triple-slash local file access attempts)
- `\evil.com` (backslash bypasses)

**Impact**:
- Potential open redirect via protocol-relative URLs
- User could be redirected to phishing sites
- Browser-dependent parsing could lead to bypasses

**Resolution**:
- ✅ Added check to block protocol-relative URLs (starting with //)
- ✅ Added backslash normalization to prevent bypass attempts
- ✅ Only allow relative paths starting with single / (not // or ///)
- ✅ Added comprehensive tests for all bypass scenarios:
  - Protocol-relative URLs blocked
  - Triple-slash URLs blocked
  - Backslash normalization working correctly
  - Relative paths not starting with / blocked (../path, ./path, etc.)
- ✅ All redirect-related tests passing

**Required for**: Security hardening

---

### M2: No Logging of Authorization Attempts
**Severity**: 🟡 MEDIUM
**File**: `src/captive_portal/api/routes/guest_portal.py`
**Lines**: 42-103

**Issue**: Authorization attempts (success/failure) are not logged to audit trail.

**Problem**:
- No record of failed authorization attempts
- Cannot detect brute-force patterns
- No audit trail for guest access
- Incident response lacks data

**Impact**:
- Security monitoring blind spot
- Compliance issues (PCI, GDPR, etc. require access logs)
- Cannot investigate suspicious activity

**Recommendation**:
- Log all authorization attempts with:
  - Timestamp
  - Client IP
  - Code type (voucher/booking)
  - Success/failure
  - Failure reason
  - User agent
- Use `AuditService` for structured logging
- Add rate limit violations to logs
- Consider SIEM integration for security events

**Required for**: Security monitoring and compliance

---

### M3: HTML Templates Not Security-Reviewed
**Severity**: 🟡 MEDIUM
**Files**:
- `src/captive_portal/web/templates/guest/authorize.html`
- `src/captive_portal/web/templates/guest/welcome.html`
- `src/captive_portal/web/templates/guest/error.html`

**Issue**: Templates include inline CSS/JavaScript and user-controlled content without explicit XSS protection documentation.

**Observations**:
- ✅ Good: Using Jinja2's auto-escaping (should prevent XSS)
- ❌ Concern: Error messages from query parameters displayed directly
- ❌ Concern: No Content-Security-Policy headers
- ❌ Concern: Inline styles/scripts violate CSP best practices

**Problem**:
- XSS risk if Jinja2 auto-escaping is misconfigured
- No defense-in-depth via CSP headers
- Error messages could reflect malicious input

**Impact**: Potential XSS vulnerabilities in guest-facing pages

**Recommendation**:
- Verify Jinja2 auto-escaping is enabled (should be by default)
- Add Content-Security-Policy headers:
  ```python
  response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'"
  ```
- Move inline CSS to external stylesheet
- Sanitize error message query parameters
- Add security headers (X-Frame-Options, X-Content-Type-Options)
- Perform manual XSS testing on error page with malicious payloads

**Required for**: Security hardening

---

### M4: Rate Limit Configuration Not Exposed in UI
**Severity**: 🟡 MEDIUM
**File**: `src/captive_portal/models/portal_config.py`
**Lines**: 10-28

**Issue**: `PortalConfig` model has rate limit settings but no UI/API to configure them.

**Problem**:
- Admins cannot adjust rate limits without database access
- Default 5 attempts/minute may be too restrictive or too lenient
- No runtime configuration capability

**Impact**:
- Operational inflexibility
- Potential lockout of legitimate guests
- Cannot adapt to attack patterns

**Recommendation**:
- Add admin UI endpoint to configure portal settings
- Add validation for reasonable limits (1-100 attempts, 10-3600 seconds)
- Add API endpoint: `PUT /admin/portal/config`
- Include rate limit settings in admin configuration page
- Document recommended values for different deployment scenarios

**Required for**: Production operability

---

### M5: Duplicate Grant Detection Not Integrated
**Severity**: 🟡 MEDIUM
**File**: `src/captive_portal/services/booking_code_validator.py`
**Lines**: 150-169

**Issue**: `check_duplicate_grant()` method exists but isn't called from authorization flow.

**Problem**:
- Multiple devices could redeem same booking code
- No enforcement of "one grant per booking" policy
- Business logic incomplete

**Specification**: "Authorization will be for an unlimited number of devices for the duration of the stay"

**Clarification Needed**: Does "unlimited devices" mean:
- A) Each booking can have multiple concurrent grants (family sharing)
- B) Each device can re-authorize multiple times (reconnections)
- C) No limit whatsoever

**Impact**:
- Potential business logic violation
- Unclear specification interpretation
- Resource exhaustion if one code creates thousands of grants

**Recommendation**:
- Clarify specification intent with stakeholder
- If limiting: integrate `check_duplicate_grant()` into authorization
- If unlimited: remove unused method to avoid confusion
- Document the decision clearly
- Add configuration option for grant limits per booking

**Required for**: Business logic clarity

---

## Low Priority Issues (Nice to Have)

### L1: Missing Internationalization (i18n)
**Severity**: 🟢 LOW
**Files**: All templates and user-facing messages

**Issue**: All text is hardcoded in English.

**Recommendation**: Add i18n support for multi-language deployments (future enhancement).

---

### L2: No Metrics/Observability
**Severity**: 🟢 LOW
**Files**: All Phase 5 routes

**Issue**: No Prometheus metrics for authorization success/failure rates, rate limit hits, etc.

**Recommendation**: Add metrics instrumentation (future enhancement).

---

### L3: HTML Template Accessibility
**Severity**: 🟢 LOW
**Files**: All guest templates

**Issue**: Templates lack ARIA labels, semantic HTML, and accessibility testing.

**Recommendation**: Add accessibility audit and improvements (future enhancement).

---

### L4: No Progressive Enhancement
**Severity**: 🟢 LOW
**Files**: Guest templates

**Issue**: Forms require JavaScript for optimal UX but degrade poorly.

**Recommendation**: Ensure forms work without JavaScript (future enhancement).

---

## Code Quality Observations

### ✅ Positive Aspects

1. **Strong Test Coverage**: 202 passing tests with good scenario coverage
2. **Clean Architecture**: Well-separated concerns (routes, services, models)
3. **Type Hints**: Comprehensive type annotations for mypy compliance
4. **Documentation**: Good docstrings with parameter descriptions
5. **Pre-commit Compliance**: All linting and formatting checks pass
6. **Error Handling**: Proper HTTP status codes and error responses
7. **Security Awareness**: Rate limiting, CSRF (for admin), input validation
8. **Modular Design**: Reusable services (UnifiedCodeService, RedirectValidator)

### ⚠️ Areas for Improvement

1. **Incomplete Implementation**: Critical TODOs in production code paths
2. **Security Gaps**: IP spoofing, missing MAC validation, XSS concerns
3. **Missing Integration**: Booking window logic exists but not used
4. **Audit Gaps**: No logging of guest authorization events
5. **Configuration**: Some features lack admin UI configuration
6. **Documentation**: Missing deployment/security considerations docs

---

## Test Coverage Analysis

**Total Tests**: 334 (202 passed, 132 skipped)
**Phase 5 Specific Tests**: ~20 integration + 15 unit tests

### Well-Tested Areas ✅
- Rate limiting (enforcement, configuration, retry-after)
- Redirect validation (whitelisting, protocol blocking)
- Booking code validation (case-insensitive, format validation)
- Captive portal detection (all platforms)
- Post-auth redirect handling

### Under-Tested Areas ⚠️
- Complete end-to-end guest authorization flow (skipped due to TODOs)
- MAC address extraction and validation
- Booking window enforcement
- Duplicate grant detection
- Error handling edge cases
- XSS/security vulnerability testing

### Skipped Tests 🟡
132 tests are skipped, mostly Phase 3/4 integration tests that require:
- Controller mocking
- Grant service completion
- Voucher redemption completion

**Recommendation**: Address skipped tests before Phase 6 to prevent technical debt accumulation.

---

## Performance Considerations

### Potential Issues
1. **Rate Limiter Memory**: Unbounded growth in high-traffic scenarios
2. **Database Queries**: No index verification on case-insensitive lookups
3. **Template Rendering**: Inline CSS could be cached

### Recommendations
- Add database index on `LOWER(slot_code)`, `LOWER(slot_name)` for performance
- Implement rate limiter cleanup task
- Profile authorization endpoint under load (1000+ req/sec)
- Consider Redis-based rate limiting for distributed deployments

---

## Security Checklist

- [x] Input validation (codes, URLs)
- [x] Rate limiting (basic implementation)
- [ ] CSRF protection on guest forms (CRITICAL - admin forms only currently)
- [x] SQL injection protection (SQLModel/SQLAlchemy ORM)
- [ ] XSS protection verification (templates need review)
- [ ] IP spoofing protection (CRITICAL - needs fix)
- [x] Output encoding (Jinja2 auto-escape)
- [ ] Secure headers (CSP, X-Frame-Options - missing)
- [ ] Audit logging (guest events not logged)
- [x] Password hashing (Argon2 for admin - N/A for guests)
- [ ] MAC address validation (missing)
- [ ] Session security (N/A - guests are stateless)

**Security Score**: 6/12 implemented (50%)

---

## Deployment Blockers

The following MUST be resolved before production deployment:

1. ✅ **Pre-commit passing** - DONE
2. ✅ **Tests passing** - DONE (with expected skips)
3. ✅ **MyPy passing** - DONE
4. ❌ **C1: Complete grant creation implementation** - BLOCKING
5. ❌ **C2: Fix IP spoofing vulnerability** - BLOCKING
6. ❌ **C3: Add CSRF protection to guest forms** - BLOCKING
7. ❌ **H2: Implement MAC address capture** - BLOCKING
8. ❌ **H3: Integrate booking window validation** - BLOCKING

**Status**: 🔴 NOT READY FOR PRODUCTION

---

## Recommendations Summary

### Immediate Actions (Before Merge)
1. Complete grant creation implementation (C1)
2. Fix IP detection security issue (C2)
3. Add CSRF protection to guest forms (C3)
4. Implement MAC address capture (H2)
5. Integrate booking window validation (H3)
6. Fix rate limiter memory leak (H1)
7. Add authorization attempt logging (M2)

### Short-term (Next Sprint)
1. Address remaining H/M priority issues
2. Add admin UI for portal configuration
3. Complete security header implementation
4. Add comprehensive XSS testing
5. Fix redirect validation edge cases
6. Document deployment security requirements

### Long-term (Future Phases)
1. Add i18n support
2. Implement metrics/observability
3. Accessibility improvements
4. Progressive enhancement
5. Redis-based distributed rate limiting

---

## Conclusion

Phase 5 implementation demonstrates good code structure, testing practices, and architectural decisions. However, **critical security vulnerabilities and incomplete functionality block production readiness**. The guest authorization flow validates codes but doesn't actually grant network access, and several security controls (IP validation, CSRF, MAC tracking) are missing or ineffective.

**Verdict**: ⚠️ CONDITIONAL APPROVAL - Fix critical issues C1-C3 and high-priority issues H1-H4 before merging.

**Estimated Effort to Address Blockers**: 2-3 days
- Grant creation integration: 4-6 hours
- Security fixes (IP, CSRF, MAC): 4-6 hours
- Booking window integration: 2-3 hours
- Testing and validation: 2-4 hours

---

**Reviewed by**: AI Code Review System
**Date**: 2025-10-30T12:35:59Z
**Signature**: Automated review - human approval required for production deployment
