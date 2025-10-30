<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Guest Authorization Flow (FR-018)

**Version**: 1.0
**Date**: 2025-10-29
**Status**: Phase 5 Implementation Complete

---

## Overview

This document describes the guest-facing captive portal authorization flow, covering voucher redemption, booking code validation, rate limiting, and post-authorization redirect handling.

## Authorization Methods

Guests can authorize their devices using two methods:

1. **Voucher Codes**: Admin-created alphanumeric codes (default 10 chars, configurable 4-24)
2. **Booking Codes**: Retrieved from Home Assistant Rental Control integrations

Both code types are entered in a single unified input field - the system automatically detects the code type.

---

## Access Methods (D18)

### Direct URL Access
- URL: `https://<portal-host>/guest/authorize`
- Accessible anytime, even if device already authorized
- Supports `?continue=<url>` query parameter for post-auth redirect

### Captive Portal Detection Redirects

The system responds to standard captive portal detection URLs:

| Platform | Detection URLs | Behavior |
|----------|---------------|----------|
| Android | `/generate_204`, `/gen_204` | 302 redirect to `/guest/authorize` |
| Windows | `/connecttest.txt`, `/ncsi.txt` | 302 redirect to `/guest/authorize` |
| Apple | `/hotspot-detect.html`, `/library/test/success.html` | 302 redirect to `/guest/authorize` |
| Firefox | `/success.txt` | 302 redirect to `/guest/authorize` |

When captive portal detection triggers, the guest's browser is automatically redirected to the authorization form.

---

## Authorization Form (D19)

### Unified Input Field

The authorization form presents a single input field for all code types:

```html
<input type="text" name="code" placeholder="Enter your code" required>
```

**Code Type Detection**:
- **Voucher format**: Alphanumeric (A-Z0-9), length 4-24 characters
- **Booking code format**: Varies by HA integration, typically slot_code or slot_name
- Backend auto-detects type based on format and database lookup

**Case Sensitivity (D19)**:
- Guest input: **Case-insensitive** matching for better UX
- Storage: Codes stored in **original case-sensitive** format
- Admin display: Shows case-sensitive values for cross-referencing with booking systems

---

## Device and Bandwidth Policy

**Unlimited Access**: Guest authorizations have no device limits or bandwidth restrictions:
- **No device limit**: Guests can authorize unlimited devices during their stay (family/group sharing)
- **No bandwidth limit**: No QoS or traffic shaping applied to authorized clients
- **Duration-based**: Access is time-limited to the booking window (with grace period) or voucher lifetime

This policy prioritizes guest convenience over resource control. Future phases may add optional admin-configurable bandwidth limits.

---

## Validation Flow

### 1. Rate Limiting (D20)

**Before** validation, check rate limits:

```
Client IP → Rate Limiter → Check attempts in last 60 seconds
            ↓
         < 5 attempts? → Proceed to validation
         ≥ 5 attempts? → HTTP 429 (Too Many Requests)
```

**Configuration**:
- Default: 5 attempts per minute per IP
- Admin-configurable: 1-100 attempts
- Window: 10-3600 seconds (default: 60)
- Storage: In-memory, rolling window

**429 Response**:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
Content-Type: application/json

{
  "detail": "Too many authorization attempts. Please try again later."
}
```

### 2. Code Validation

After rate limit check passes, validate the code:

#### Voucher Validation
1. Format check: Alphanumeric, length 4-24
2. Database lookup (case-insensitive match)
3. Check `uses_remaining > 0` and `expires_after > now()`
4. Decrement `uses_remaining`
5. Create `AccessGrant` with voucher-based lifetime
6. Emit metrics: `voucher_redemptions_total`
7. Audit log: Action=voucher_redeemed

#### Booking Code Validation
1. Format check: Matches expected pattern for selected `identifier_attr`
2. Fetch HA integration events (0-N)
3. Match code against selected attribute (slot_code, slot_name, or last_four)
4. Case-insensitive match
5. Validate booking window:
   - Current time within `[start - 24h, end + checkout_grace_minutes]`
   - If past checkout, apply grace period (D22)
6. Check for duplicate grant (prevent multi-device abuse for same booking)
7. Create `AccessGrant` with booking-based lifetime
8. Emit metrics: `booking_authorizations_total`
9. Audit log: Action=booking_authorized

---

## Error Scenarios (FR-018)

| Error Code | Scenario | HTTP Status | User Message | Admin Visibility |
|------------|----------|-------------|--------------|------------------|
| `invalid_format` | Code doesn't match voucher/booking patterns | 400 | "Invalid authorization code" | Audit log |
| `not_found` | Code not in vouchers or HA events | 404 | "Code not found or expired" | Audit log |
| `outside_window` | Booking code outside check-in/out window | 410 | "Authorization window has closed" | Audit log + metrics |
| `duplicate` | Device already authorized for this booking | 409 | "Device already authorized" | Audit log |
| `integration_unavailable` | HA integration offline/unreachable | 503 | "Service temporarily unavailable" | Alert + audit log |
| `rate_limited` | Too many attempts from IP | 429 | "Too many attempts. Try again later." | Metrics |

---

## Grace Period (D22)

For booking-based grants, extend access after checkout:

**Configuration**:
- Default: 15 minutes
- Max: 30 minutes
- Admin-configurable per HA integration

**Calculation**:
```python
if current_time > booking.end:
    effective_end = booking.end + timedelta(minutes=grace_minutes)
    if current_time > effective_end:
        raise BookingOutsideWindowError("checkout_grace_expired")
    # Within grace period - grant access
```

**Display**:
- Grant list shows: "Grace period: 12 min remaining"
- Auto-revokes at grace period expiration

---

## Post-Authorization Redirect (D21)

After successful authorization, redirect guest:

### Priority Order
1. **Validate `continue` parameter** (if present):
   - Must pass open redirect checks
   - Whitelisted external domains only
   - Internal paths always allowed
2. **Admin-configured success URL** (default: `/guest/welcome`)
3. **Fallback**: `/guest/welcome`

**Configuration**:
```python
# models/portal_config.py
success_redirect_url: str = "/guest/welcome"
```

**Redirect Validation** (`RedirectValidator`):
- Block external URLs unless whitelisted
- Prevent `javascript:`, `data:`, `file:` schemes
- Validate URL structure (RFC 3986)

---

## Success Response

### HTTP 303 Redirect
```http
HTTP/1.1 303 See Other
Location: /guest/welcome
Set-Cookie: access_token=...; Secure; HttpOnly; SameSite=Lax
```

### Welcome Page
- Shows success message
- Connection details (device authorized, access valid for stay duration)
- "Close this window" link

---

## Metrics Emitted

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `voucher_redemptions_total` | Counter | `result=[success,failure]` | Voucher redemption attempts |
| `booking_authorizations_total` | Counter | `result=[success,failure],integration_id` | Booking code attempts |
| `rate_limit_rejections_total` | Counter | - | 429 responses |
| `authorization_errors_total` | Counter | `error_type` | Errors by type (invalid_format, not_found, etc.) |

---

## Audit Log Events

All authorization attempts are logged:

```json
{
  "event_id": "uuid",
  "timestamp_utc": "2025-10-29T12:34:56.789Z",
  "user": "guest",
  "action": "voucher_redeemed",
  "resource": "voucher:ABC123DEF4",
  "result": "success",
  "correlation_id": "req-uuid",
  "ip_address": "192.168.1.100",
  "device_id": "Mozilla/5.0..."
}
```

Actions: `voucher_redeemed`, `booking_authorized`, `authorization_failed`

---

## Implementation Files

### Routes
- `api/routes/guest_portal.py`: Authorization form, POST handler, welcome page
- `api/routes/captive_detect.py`: Captive portal detection redirects

### Templates
- `web/templates/guest/authorize.html`: Authorization form
- `web/templates/guest/welcome.html`: Post-auth success page
- `web/templates/guest/error.html`: Error page

### Services
- `services/unified_code_service.py`: Auto-detect voucher vs booking code
- `services/booking_code_validator.py`: Booking validation logic + grace period
- `services/redirect_validator.py`: Post-auth redirect validation

### Security
- `security/rate_limiter.py`: Per-IP rate limiting
- `web/middleware/rate_limit_middleware.py`: FastAPI middleware

### Models
- `models/portal_config.py`: Portal configuration (rate limits, success redirect)
- `models/access_grant.py`: Access grant with device_id, integration_id fields

---

## Phase 5 Decisions Reference

All implementation decisions documented in `phase5_decisions.md`:

- **D18**: Both direct + redirect access methods
- **D19**: Unified input field, case-insensitive matching
- **D20**: Admin-configurable rate limiting (default 5/min per IP)
- **D21**: Admin-configurable redirect (default to original destination)
- **D22**: Checkout grace period (default 15 min, max 30 min)

---

**Document Control**
**Last Updated**: 2025-10-29T20:00:00Z
**Next Review**: Phase 6 (Performance & Hardening)
