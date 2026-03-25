<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Audit Logging Review — Captive Portal

This document reviews the audit logging implementation, catalogues all
audited actions, and identifies gaps where security-relevant events are
not yet recorded.

---

## 1. Audit Infrastructure

### Service

**File:** `src/captive_portal/services/audit_service.py`

`AuditService` provides both generic and specialised logging methods:

| Method | Purpose |
|--------|---------|
| `log()` | Generic audit entry (actor, action, outcome, meta) |
| `log_voucher_created()` | Voucher creation with duration and booking ref |
| `log_voucher_redeemed()` | Voucher redemption (actor = `guest:{mac}`) |
| `log_grant_extended()` | Grant extension with new end time |
| `log_grant_revoked()` | Grant revocation with reason |
| `log_rbac_denied()` | Permission denial (sets `rbac_denial: True` in meta) |
| `log_admin_action()` | Generic admin action with arbitrary metadata |

Actions use string identifiers with dot-notation (e.g.,
`voucher.create`, `grant.revoke`, `guest.authorize`). There is no enum
class — action names are conventions.

### Database Model

**File:** `src/captive_portal/models/audit_log.py`

| Field | Type | Max Length | Indexed | Notes |
|-------|------|-----------|---------|-------|
| `id` | UUID | — | PK | Immutable |
| `actor` | str | 128 | Yes | Username, `system`, or `guest:{mac}` |
| `role_snapshot` | str \| None | 32 | No | Actor's role at time of action |
| `action` | str | 64 | Yes | Dot-notation action identifier |
| `target_type` | str \| None | 32 | No | Entity type (voucher, grant, etc.) |
| `target_id` | str \| None | 128 | No | Entity identifier |
| `timestamp_utc` | datetime | — | Yes | UTC, set at creation |
| `outcome` | str | 32 | No | success / failure / denied / error / rate_limited |
| `meta` | JSON \| None | — | No | IP, user-agent, error details, reason |

### Retention

**Config model:** `src/captive_portal/models/audit_config.py`
**Cleanup:** `src/captive_portal/services/audit_cleanup_service.py`

- Default retention: 30 days (configurable 1-90)
- Cleanup deletes records where `timestamp_utc < now - retention_days`

---

## 2. Audited Actions

### 2.1 Admin Login

**File:** `src/captive_portal/api/routes/admin_auth.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Login success (line 115) | `success` | `ip_address`, `target_id=session_id` |
| Login failure (line 82) | `failure` | `reason: invalid_credentials` |

**Fields passed:** actor (username), action (`admin.login`),
target_type (`session`), target_id, outcome, meta.

### 2.2 Guest Authorization

**File:** `src/captive_portal/api/routes/guest_portal.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Rate limited (line 270) | `rate_limited` | `client_ip`, `user_agent`, `retry_after` |
| MAC extraction failed (line 292) | `error` | `error: mac_extraction_failed`, `detail` |
| Invalid code format (line 310) | `denied` | `error: invalid_code_format`, `mac`, `detail` |
| Voucher redemption failed (line 423) | `denied` | `error: voucher_redemption_failed`, `mac` |
| Booking not found (line 443) | `denied` | `error: booking_not_found`, `mac` |
| Booking outside window (line 463) | `denied` | `error: booking_outside_window`, `mac` |
| Duplicate grant (line 483) | `denied` | `error: duplicate_grant`, `mac` |
| Integration unavailable (line 503) | `error` | `error: integration_unavailable` |
| Authorization success (line 524) | `success` | `client_ip`, `mac`, `user_agent`, `target_id=grant.id` |

### 2.3 Voucher Management

**File:** `src/captive_portal/api/routes/vouchers.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Voucher created (line 80) | `success` | `duration_minutes`, `booking_ref` |

Uses `log_admin_action()` with action `create_voucher`.

### 2.4 Grant Management

**File:** `src/captive_portal/api/routes/grants.py`

| Event | Outcome | Meta |
|-------|---------|------|
| List grants (line 120) | `success` | `status_filter`, `count` |
| Extend grant (line 218) | `success` | `additional_minutes`, `new_end_utc` |
| Revoke grant (line 271) | `success` | — |

### 2.5 Integration Management

**Files:** `src/captive_portal/api/routes/integrations.py`,
`src/captive_portal/api/routes/integrations_ui.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Create integration (integrations.py line 142) | `success` | `integration_id`, `identifier_attr`, `checkout_grace_minutes` |
| Create integration (integrations_ui.py line 165) | `success` | — |
| Update integration (integrations_ui.py line 147) | `success` | — |
| Delete integration (integrations_ui.py line 208) | `success` | — |

### 2.6 Portal Configuration

**File:** `src/captive_portal/api/routes/portal_settings_ui.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Config update (line 185) | `success` | `rate_limit_attempts`, `rate_limit_window_seconds`, `redirect_to_original_url` |

### 2.7 System Maintenance

**File:** `src/captive_portal/services/cleanup_service.py`

| Event | Outcome | Meta |
|-------|---------|------|
| Expired event cleanup (line 62) | `success` | `deleted_count`, `cutoff_date` |

Actor is `system`.

---

## 3. Gap Analysis

### 3.1 Critical Gaps (HIGH severity)

#### G-01: Admin Logout Not Audited

**File:** `admin_auth.py` lines 133-158

The logout endpoint destroys the session and clears cookies but does not
create an audit entry. Session destruction is a security-relevant event.

**Recommendation:** Add `audit_service.log()` with
action=`admin.logout`, outcome=`success`, actor=admin username,
target_type=`session`, target_id=session_id.

#### G-02: Admin Bootstrap Not Audited

**File:** `admin_auth.py` lines 161-199

The bootstrap endpoint creates the initial administrator account. This
is a critical security event that is not logged.

**Recommendation:** Add `audit_service.log()` with
action=`admin.bootstrap`, outcome=`success`, actor=`system`,
target_type=`admin_user`, target_id=new admin username.

#### G-03: Admin Account CRUD Not Audited

**File:** `admin_accounts.py`

| Operation | Lines | Audited? |
|-----------|-------|----------|
| Create account | 103-153 | ❌ No |
| Update account | 156-204 | ❌ No |
| Delete account | 207-238 | ❌ No |

No audit entries are created when admin accounts are created, modified
(including password changes), or deleted.

**Recommendation:** Add audit entries for each operation with
action=`admin.create` / `admin.update` / `admin.delete`, capturing the
target admin username and what fields were changed (excluding password
values).

#### G-04: RBAC Denials Not Consistently Audited

**Files:** `portal_settings_ui.py` lines 131-135,
`portal_config.py` lines 111-114

When a user with insufficient permissions attempts a restricted action,
the application returns 403 but does not call `log_rbac_denied()`.

**Recommendation:** Call `audit_service.log_rbac_denied()` before
returning 403 in all permission-gated endpoints.

### 3.2 Medium Gaps

#### G-05: Booking Authorization Not Audited

**File:** `api/routes/booking_authorize.py` lines 78-195

The booking-based guest authorization flow has no audit logging at all.
This is a separate code path from the voucher-based guest flow in
`guest_portal.py` (which **is** audited).

**Recommendation:** Mirror the audit logging from `guest_portal.py` to
cover all booking authorization outcomes (success, denied, error).

#### G-06: Session Validation Failures Not Audited

**File:** `admin_accounts.py` lines 60-73

When `get_current_admin()` fails to find a valid session, it returns
401 without logging. Repeated 401 responses may indicate a session
hijack attempt.

**Recommendation:** Log with action=`admin.session_invalid`,
outcome=`denied`, including IP and user-agent from the request.

#### G-07: Audit Configuration Changes Not Audited

**File:** `api/routes/audit_config.py` lines 43-64

Changes to the audit retention policy are not logged. An attacker with
admin access could reduce the retention period to erase evidence.

**Recommendation:** Log with action=`audit_config.update`,
outcome=`success`, capturing the old and new retention values.

### 3.3 Low Gaps

#### G-08: Grant Revocation Metadata Incomplete

**File:** `grants.py` line 271

The revoke grant audit entry does not include a `reason` or the
`metadata` dict. The `log_admin_action()` call passes `metadata=None`.

**Recommendation:** Accept an optional reason from the request and pass
it through to the audit metadata.

#### G-09: Read-Only Access Not Logged

**File:** `portal_config.py` lines 67-95

GET requests to read portal configuration are not logged. This is
acceptable for most deployments but may be desired in high-security
environments.

**Recommendation:** Consider optional verbose audit mode.

---

## 4. Field Coverage Summary

The table below summarises whether each audited action includes the
recommended fields.

| Action | actor | action | target | outcome | IP | user-agent | correlation_id |
|--------|:-----:|:------:|:------:|:-------:|:--:|:----------:|:--------------:|
| admin.login (success) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| admin.login (failure) | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| guest.authorize | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| create_voucher | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| extend_grant | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| revoke_grant | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| portal_config.update | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| event.cleanup | ✅ | ✅ | ❌ | ✅ | N/A | N/A | ❌ |

**Key observations:**

- **IP address** is only captured for login success and guest
  authorization events. Admin modification actions do not record IP.
- **User-agent** is only captured for guest authorization events.
- **correlation_id** is not implemented in the current `AuditLog` model.
  The README mentions correlation IDs as an architecture principle but
  the field is not present in the schema.

---

## 5. Recommendations Summary

| Priority | ID | Action |
|----------|-----|--------|
| 🔴 HIGH | G-01 | Audit admin logout |
| 🔴 HIGH | G-02 | Audit admin bootstrap |
| 🔴 HIGH | G-03 | Audit admin account CRUD |
| 🔴 HIGH | G-04 | Audit RBAC denials consistently |
| 🟡 MEDIUM | G-05 | Audit booking authorization |
| 🟡 MEDIUM | G-06 | Audit session validation failures |
| 🟡 MEDIUM | G-07 | Audit config retention changes |
| 🟠 LOW | G-08 | Add reason to grant revocation |
| 🟠 LOW | G-09 | Optional verbose audit mode |
| — | — | Add `correlation_id` field to `AuditLog` model |
| — | — | Capture IP address for all admin actions |
| — | — | Capture user-agent for admin actions |
