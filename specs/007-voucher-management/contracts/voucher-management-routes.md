SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Voucher Management Routes Contract

**Feature**: 007-voucher-management | **Date**: 2025-07-18

This document defines the contracts for all new voucher management routes. These routes extend the existing `/admin/vouchers` prefix and follow the Post/Redirect/Get (PRG) pattern established by the grants page.

All routes require admin authentication (via `SessionMiddleware` → `require_admin` dependency). All responses include cache-control headers. All state-changing POST routes validate CSRF tokens.

---

## GET /admin/vouchers (modified)

**Purpose**: Display voucher list with action controls, selection checkboxes, and bulk actions.
**Authentication**: Required
**Response**: `200 OK` — `text/html`
**Changes from existing**: Adds action columns (revoke/delete buttons), checkbox column, bulk action bar, `voucher_actions` context variable.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `new_code` | str | No | — | Newly created voucher code to highlight |
| `success` | str | No | — | Success feedback message |
| `error` | str | No | — | Error feedback message |

### Template Context (additions)

| Variable | Type | Description |
|----------|------|-------------|
| `vouchers` | list[Voucher] | All vouchers, ordered by `created_utc` DESC, limit 500 |
| `csrf_token` | str | CSRF token for all forms |
| `voucher_actions` | dict[str, VoucherActions] | Per-voucher eligibility: `.can_revoke`, `.can_delete` |
| `new_code` | str or None | Newly created code to highlight |
| `success_message` | str or None | Flash success message |
| `error_message` | str or None | Flash error message |

### Voucher Action Eligibility

For each voucher, the `voucher_actions` dict provides:
- `can_revoke`: True when `status not in {REVOKED, EXPIRED}` and `now <= expires_utc`
- `can_delete`: True when `redeemed_count == 0`

---

## POST /admin/vouchers/revoke/{code}

**Purpose**: Revoke a single voucher (FR-001–FR-005).
**Authentication**: Required
**CSRF**: Required (double-submit cookie pattern)
**Content-Type**: `application/x-www-form-urlencoded`

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | str | Voucher code (PK, 4-24 chars, A-Z0-9) |

### Form Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | str | Yes | CSRF protection token |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| Success | 303 | `/admin/vouchers/?success=Voucher+{CODE}+revoked+successfully` |
| Already revoked (idempotent) | 303 | `/admin/vouchers/?success=Voucher+{CODE}+revoked+successfully` |
| Voucher not found | 303 | `/admin/vouchers/?error=Voucher+not+found` |
| Voucher expired | 303 | `/admin/vouchers/?error=Cannot+revoke+an+expired+voucher` |
| Invalid CSRF | 303 | `/admin/vouchers/?error=Invalid+CSRF+token` |

### Audit Log Entry
- `action`: `"voucher.revoke"`
- `target_type`: `"voucher"`
- `target_id`: voucher code
- Audit logged by route handler after any non-error service return (including idempotent revoke), following the `grants_ui.py` pattern where audit logging lives in the route handler, not the service layer

---

## POST /admin/vouchers/delete/{code}

**Purpose**: Permanently delete a single voucher (FR-006–FR-010).
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | str | Voucher code (PK) |

### Form Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | str | Yes | CSRF protection token |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| Success | 303 | `/admin/vouchers/?success=Voucher+{CODE}+deleted+successfully` |
| Voucher redeemed | 303 | `/admin/vouchers/?error=Cannot+delete+voucher+{CODE}+—+it+has+been+redeemed` |
| Voucher not found | 303 | `/admin/vouchers/?error=Voucher+not+found` |
| Invalid CSRF | 303 | `/admin/vouchers/?error=Invalid+CSRF+token` |

### Audit Log Entry
- `action`: `"voucher.delete"`
- `target_type`: `"voucher"`
- `target_id`: voucher code
- `meta`: `{"status_at_delete": "<status>", "booking_ref": "<ref or null>"}`
- Implementation note: snapshot `status_at_delete` and `booking_ref`, perform the predicate-based hard delete, then log this entry **after** a successful delete using the snapshot values.
- Audit logged by route handler (not the service layer) after successful service return, following the `grants_ui.py` pattern.

---

## POST /admin/vouchers/bulk-revoke

**Purpose**: Revoke multiple selected vouchers (FR-013, FR-015).
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | str | Yes | CSRF protection token |
| `codes` | list[str] | Yes | Selected voucher codes (from checkboxes) |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| All revoked | 303 | `/admin/vouchers/?success=Revoked+N+vouchers+successfully` |
| Partial success | 303 | `/admin/vouchers/?success=Revoked+N+vouchers,+skipped+M+(reason+details)` |
| All skipped | 303 | `/admin/vouchers/?error=No+vouchers+revoked+—+N+skipped+(reason+details)` |
| None selected (FR-016) | 303 | `/admin/vouchers/?error=No+vouchers+selected` |
| Invalid CSRF | 303 | `/admin/vouchers/?error=Invalid+CSRF+token` |

### Skip Reasons
- `"expired"`: voucher expired (`now > expires_utc`)
- `"already revoked"`: voucher already in REVOKED status (counted as skip, not error)
- `"not found"`: voucher code no longer exists

### Audit Log
One entry per successfully revoked voucher (same as single revoke).

---

## POST /admin/vouchers/bulk-delete

**Purpose**: Delete multiple selected vouchers (FR-014, FR-015).
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | str | Yes | CSRF protection token |
| `codes` | list[str] | Yes | Selected voucher codes (from checkboxes) |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| All deleted | 303 | `/admin/vouchers/?success=Deleted+N+vouchers+successfully` |
| Partial success | 303 | `/admin/vouchers/?success=Deleted+N+vouchers,+skipped+M+(reason+details)` |
| All skipped | 303 | `/admin/vouchers/?error=No+vouchers+deleted+—+N+skipped+(reason+details)` |
| None selected (FR-016) | 303 | `/admin/vouchers/?error=No+vouchers+selected` |
| Invalid CSRF | 303 | `/admin/vouchers/?error=Invalid+CSRF+token` |

### Skip Reasons
- `"already redeemed"`: voucher has `redeemed_count > 0`
- `"not found"`: voucher code no longer exists

### Audit Log
One entry per successfully deleted voucher (same as single delete, with meta).

---

## Cross-Cutting Behaviors

### CSRF Pattern
All POST routes validate CSRF using the existing double-submit cookie pattern:
1. Token from form field `csrf_token` must match token from `csrftoken` cookie
2. Comparison uses `secrets.compare_digest()` (constant-time)
3. On failure: redirect with `?error=Invalid+CSRF+token`

### Authentication
All routes use `require_admin` dependency. Unauthenticated requests return `401 Unauthorized`.

### Ingress Root Path
All redirects prefixed with `request.scope.get("root_path", "")`.

### Cache-Control Headers
Applied by existing `SecurityHeadersMiddleware` to all `/admin/*` paths:
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```

### SPDX Headers
All new/modified source files include:
```
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
```
