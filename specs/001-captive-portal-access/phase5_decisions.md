<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Phase 5 Decisions: Guest Portal & Authentication

**Date**: 2025-10-29T18:42:00Z
**Phase**: Phase 5 - Guest Portal & Authentication
**Status**: ✅ DECISIONS APPROVED

---

## Overview

Phase 5 implements the guest-facing captive portal with authentication via vouchers and booking codes, rate limiting, and post-authentication redirect handling. This document records all decisions made to enable Phase 5 implementation.

---

## Decisions Approved

### D18: Guest Authorization Form Access Methods ✅ APPROVED
**Context**: How guests access the authorization form

**Decision**: Both direct access + redirect from any captive portal detection attempt

**Rationale**:
- Covers all ways guests may arrive at the portal
- Direct URL access for tech-savvy users
- Automatic redirect for standard captive portal detection
- Handles both browser-initiated and OS-initiated detection

**Implementation**:
- Direct route: `/guest/authorize` (always accessible)
- Redirect route: Catch-all for common captive portal detection URLs
- Detection URLs: `/generate_204`, `/connecttest.txt`, `/hotspot-detect.html`, etc.
- All detection URLs redirect to `/guest/authorize` with original destination preserved

**Files**:
- `src/captive_portal/web/routes/guest_portal.py`
- `src/captive_portal/web/routes/captive_detect.py`

---

### D19: Authorization Code Input Method ✅ APPROVED
**Context**: How guests enter voucher/booking codes

**Decision**: Single unified input field (auto-detect code type)

**Rationale**:
- Simplest UX for guests (no decision required)
- Backend distinguishes voucher vs booking code by format
- Vouchers: Alphanumeric (A-Z0-9), configurable length (4-24, default 10)
- Booking codes: From HA integration, slot_code or slot_name (admin choice)
- Clear error messages if code format invalid

**Implementation**:
- Form: Single `<input type="text" name="code">` field
- Validation: Try voucher format first, then booking code lookup
- Error handling: "Invalid authorization code" (generic for security)
- Case sensitivity: All guest input case-insensitive for matching
- Storage/Display: Codes stored and displayed to admin in original case-sensitive format

**File**: `src/captive_portal/web/templates/guest/authorize.html`

---

### D20: Rate Limiting Strategy ✅ APPROVED
**Context**: Prevent brute-force attacks on authorization codes

**Decision**: Admin-configurable rate limiting with default 5 attempts/minute per IP

**Rationale**:
- Prevents automated brute-force attacks
- Per-IP tracking (simpler than per-session)
- Configurable for different network environments
- 5 attempts/minute balances security and guest convenience

**Implementation**:
- Storage: In-memory dict `{ip: [(timestamp, attempts), ...]}`
- Window: Rolling 60-second window
- Config: `RATE_LIMIT_ATTEMPTS=5`, `RATE_LIMIT_WINDOW_SECONDS=60`
- Response: 429 Too Many Requests with Retry-After header
- Cleanup: Purge entries older than window every 5 minutes

**Files**:
- `src/captive_portal/security/rate_limiter.py`
- `src/captive_portal/web/middleware/rate_limit_middleware.py`

---

### D21: Post-Authentication Redirect Behavior ✅ APPROVED
**Context**: Where to send guests after successful authorization

**Decision**: Admin-configurable with default to original destination URL

**Rationale**:
- Default behavior: Return to originally requested page
- Fallback: Configurable success page (e.g., property website, WiFi instructions)
- Preserves original intent (user was navigating to specific URL)
- Admin can override for branding or instructions

**Implementation**:
- Capture: `?continue=<url>` query parameter from redirect
- Validation: Whitelist external domains (prevent open redirect)
- Default: Return to `continue` URL if present and valid
- Fallback: Redirect to admin-configured success URL (default: `/guest/welcome`)
- Config: `SUCCESS_REDIRECT_URL=/guest/welcome`

**Files**:
- `src/captive_portal/web/routes/guest_portal.py`
- `src/captive_portal/models/portal_config.py` (add success_redirect_url field)

---

### D22: End of Stay Grace Period ✅ APPROVED
**Context**: Allow guests brief internet access after checkout for final arrangements

**Decision**: Admin-configurable grace period with default 15 minutes, max 30 minutes

**Rationale**:
- Guests need to coordinate pickup, call ride services, etc.
- 15 minutes is sufficient for most use cases
- 30-minute max prevents abuse
- Admin can disable (set to 0) if not wanted

**Implementation**:
- Field: `HAIntegrationConfig.checkout_grace_minutes` (default: 15, max: 30)
- Calculation: When `current_time > booking.end`, extend effective end by grace period
- Display: Show grace period status in grant list ("Grace period: 12 min remaining")
- Auto-cleanup: Grant expires after grace period ends

**Files**:
- `src/captive_portal/models/ha_integration_config.py`
- `src/captive_portal/services/grant_service.py` (update extend/revoke logic)

---

## Device and Bandwidth Policy Clarification

**Unlimited Access Definition**: Guest authorizations have no device limits or bandwidth restrictions:
- **No device limit**: Each booking/voucher can authorize unlimited devices during its validity period
- **No bandwidth limit**: No QoS throttling or traffic shaping applied to authorized clients
- **Justification**: Family/group sharing (multiple devices per booking), guest convenience priority
- **Implementation**: No duplicate grant checking, no device count limits, no bandwidth enforcement

This policy means the `check_duplicate_grant()` method in `BookingCodeValidator` is intentionally unused. Future phases may add optional admin-configurable limits.

---

## Database Schema Changes Required

### Phase 5 Additions

#### PortalConfig Model Updates
```python
class PortalConfig(SQLModel, table=True):
    """Guest portal configuration."""
    # Existing fields...

    # D21: Post-auth redirect
    success_redirect_url: str = Field(default="/guest/welcome")

    # D20: Rate limiting
    rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
```

#### HAIntegrationConfig Model Updates
```python
class HAIntegrationConfig(SQLModel, table=True):
    """Home Assistant integration configuration."""
    # Existing fields...

    # D22: Grace period
    checkout_grace_minutes: int = Field(default=15, ge=0, le=30)
```

---

## Implementation Scope

Phase 5 will deliver:
1. **Guest Portal Routes**: `/guest/authorize`, `/guest/welcome`, captive portal detection redirects
2. **Authorization Logic**: Voucher validation, booking code lookup, device authorization
3. **Rate Limiting**: Per-IP rate limiting with configurable thresholds
4. **Post-Auth Redirect**: Original destination redirect with admin fallback
5. **Grace Period**: Checkout grace period for booking-based grants
6. **Templates**: Guest authorization form, success page, error pages
7. **Middleware**: Rate limiting, captive portal detection
8. **Database Migrations**: PortalConfig and HAIntegrationConfig updates

---

**Approver**: User (tykeal@bardicgrove.org)
**Date**: 2025-10-29T18:42:00Z
**Status**: ✅ ALL DECISIONS APPROVED - READY FOR PHASE 5 IMPLEMENTATION
