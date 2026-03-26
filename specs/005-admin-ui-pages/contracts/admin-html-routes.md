SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Admin HTML Routes Contract

**Feature**: 005-admin-ui-pages | **Date**: 2025-07-16

This document defines the contracts for all HTML-serving admin routes added by this feature. These routes serve Jinja2-rendered HTML pages and process form submissions using the Post/Redirect/Get (PRG) pattern.

All routes require admin authentication (via `SessionMiddleware` → `require_admin` dependency) unless explicitly noted. All responses include cache-control headers per FR-028.

---

## GET /admin/dashboard

**Purpose**: Display admin dashboard with statistics and recent activity (FR-001–FR-004).
**Authentication**: Required (redirect to `/admin/login` if unauthenticated)
**Response**: `200 OK` — `text/html`

### Template Context

| Variable | Type | Description |
|----------|------|-------------|
| `stats` | DashboardStats | Object with `.active_grants`, `.pending_grants`, `.available_vouchers`, `.integrations` (all int) |
| `recent_logs` | list[ActivityLogEntry] | Up to 20 entries, each with `.timestamp`, `.action`, `.target_type`, `.target_id`, `.admin_username` |
| `csrf_token` | str | CSRF token for CSRF-protected forms on the dashboard; provided for consistency even though `/admin/logout` is CSRF-exempt and does not require it |

### Response Headers
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```

### Empty States
- All stats fields return `0` when no data exists (never `null` or error)
- `recent_logs` returns empty list `[]` → template displays "No recent activity"

---

## GET /admin/grants

**Purpose**: Display grant list with filters (FR-005–FR-007).
**Authentication**: Required
**Response**: `200 OK` — `text/html`

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `status` | str | No | `""` (all) | Filter: `pending`, `active`, `expired`, `revoked`, or empty for all |
| `success` | str | No | — | Success feedback message (set by PRG redirect) |
| `error` | str | No | — | Error feedback message (set by PRG redirect) |

### Template Context

| Variable | Type | Description |
|----------|------|-------------|
| `grants` | list[AccessGrant] | Grants with status re-computed at render time, ordered by `created_utc` DESC |
| `status_filter` | str | Current filter value (for select element pre-selection) |
| `csrf_token` | str | CSRF token for extend/revoke/logout forms |
| `success_message` | str or None | Flash success message |
| `error_message` | str or None | Flash error message |

### Empty State
- When `grants` is empty: display "No grants found for the selected filter."

---

## POST /admin/grants/extend/{grant_id}

**Purpose**: Extend a grant's duration (FR-008, FR-010, FR-011, FR-012).
**Authentication**: Required
**CSRF**: Required (double-submit cookie pattern)
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `csrf_token` | str | Yes | Must match cookie | CSRF protection token |
| `minutes` | int | Yes | 1–1440 | Minutes to extend |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| Success | 303 | `/admin/grants?success=Grant+extended+by+{N}+minutes` |
| Grant not found | 303 | `/admin/grants?error=Grant+not+found` |
| Revoked grant | 303 | `/admin/grants?error=Cannot+extend+a+revoked+grant` |
| Invalid CSRF | 303 | `/admin/grants?error=Invalid+CSRF+token` |
| Invalid minutes | 303 | `/admin/grants?error=Minutes+must+be+between+1+and+1440` |

---

## POST /admin/grants/revoke/{grant_id}

**Purpose**: Revoke a grant (FR-009, FR-010, FR-011, FR-012).
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csrf_token` | str | Yes | CSRF protection token |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| Success | 303 | `/admin/grants?success=Grant+revoked+successfully` |
| Already revoked | 303 | `/admin/grants?success=Grant+revoked+successfully` (idempotent) |
| Grant not found | 303 | `/admin/grants?error=Grant+not+found` |
| Invalid CSRF | 303 | `/admin/grants?error=Invalid+CSRF+token` |

---

## GET /admin/vouchers

**Purpose**: Display voucher list and creation form (FR-013–FR-018).
**Authentication**: Required
**Response**: `200 OK` — `text/html`

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `new_code` | str | No | — | Newly created voucher code to highlight (set by PRG redirect) |
| `success` | str | No | — | Success feedback message |
| `error` | str | No | — | Error feedback message |

### Template Context

| Variable | Type | Description |
|----------|------|-------------|
| `vouchers` | list[Voucher] | All vouchers, ordered by `created_utc` DESC, limit 500 |
| `csrf_token` | str | CSRF token for create/logout forms |
| `new_code` | str or None | Newly created code to display prominently |
| `success_message` | str or None | Flash success message |
| `error_message` | str or None | Flash error message |

### Voucher Display (per FR-018)
Each voucher in the list shows:
- `code`: the voucher code
- `duration_minutes`: access duration
- `status`: raw VoucherStatus value (unused, active, expired, revoked)
- `created_utc`: creation timestamp
- **Derived redemption status**: "Unredeemed" if `redeemed_count == 0`, "Redeemed" if `redeemed_count > 0`
- If redeemed: link to associated grant (display `last_redeemed_utc`)

### Empty State
- When `vouchers` is empty: display "No vouchers found. Create one using the form above."

---

## POST /admin/vouchers/create

**Purpose**: Create a new voucher (FR-015–FR-017).
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `csrf_token` | str | Yes | Must match cookie | CSRF protection token |
| `duration_minutes` | int | Yes | 1–43200 | Access duration in minutes |
| `booking_ref` | str | No | max 128 chars | Optional booking reference |

### Responses

| Scenario | Status | Redirect |
|----------|--------|----------|
| Success | 303 | `/admin/vouchers?new_code={CODE}&success=Voucher+created+successfully` |
| Invalid CSRF | 303 | `/admin/vouchers?error=Invalid+CSRF+token` |
| Invalid duration | 303 | `/admin/vouchers?error=Duration+must+be+between+1+and+43200+minutes` |
| Code collision | 303 | `/admin/vouchers?error=Failed+to+generate+unique+voucher+code` |

---

## POST /admin/logout

**Purpose**: Terminate admin session and redirect to login (FR-019–FR-021).
**Authentication**: Not strictly required (no-op if no session exists)
**CSRF**: **Exempt** (per FR-019, FR-023)
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields

None required (CSRF-exempt). The form in the nav bar submits with no hidden fields.

### Behavior
1. Read `session_id` from `request.state`
2. If session exists: destroy session via `session_store.delete()`, delete session cookie
3. If no session: no-op (safe)
4. Redirect to `/admin/login`

### Response

| Scenario | Status | Redirect |
|----------|--------|----------|
| Session destroyed | 303 | `{root_path}/admin/login` |
| No session | 303 | `{root_path}/admin/login` |

### Response Headers
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
Set-Cookie: session_id=; Max-Age=0; ...  (cookie deletion)
```

---

## Cross-Cutting Behaviors

### Authentication Redirect
All admin HTML routes use the shared `require_admin` dependency (wired via `SessionMiddleware` or per-route dependency injection) to enforce authentication.

- If `request.state.admin_id` is present, the request is allowed to proceed.
- If `request.state.admin_id` is `None`, `require_admin` raises `HTTPException(status_code=401)`.
- For `GET /admin/*` HTML routes (except `/admin/login`), a dedicated exception handler or UI-specific dependency layer maps this `401` to:
  ```
  303 See Other → {root_path}/admin/login
  ```

This contract describes the externally observable behavior (unauthenticated `GET /admin/*` requests are redirected with `303` to the login page), while allowing the implementation to centralize the low-level `401` behavior in `require_admin` and a shared exception handler.

### Cache-Control Headers (FR-028)
Applied by `SecurityHeadersMiddleware` to all responses where `request.url.path.startswith("/admin")`:
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```

### Ingress Root Path (FR-024)
All redirects and template URLs are prefixed with `request.scope.get("root_path", "")`.

### CSRF Pattern
All state-changing POST routes (except `/admin/logout`) validate CSRF using the existing double-submit cookie pattern:
1. Token from form field `csrf_token` must match token from `csrftoken` cookie
2. Comparison uses `secrets.compare_digest()` (constant-time)
3. On failure: redirect with `?error=Invalid+CSRF+token`

### SPDX Headers (FR-027)
All new source files include:
```
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
```
