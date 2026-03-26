SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Admin UI Pages

**Feature**: 005-admin-ui-pages | **Date**: 2025-07-16

This feature does not introduce new database entities. It builds UI pages on top of existing models. This document maps the existing entities to the UI requirements and identifies new view models and service interfaces needed.

## Existing Entities (no schema changes)

### AccessGrant

**Table**: `accessgrant` | **Module**: `captive_portal.models.access_grant`

| Field | Type | UI Column | Notes |
|-------|------|-----------|-------|
| `id` | UUID (PK) | (hidden) | Used in extend/revoke form action URLs |
| `mac` | str(17) | MAC Address | Displayed as `<code>` |
| `status` | GrantStatus enum | Status | Re-computed at render time (see below) |
| `booking_ref` | str(128), nullable | Booking Ref | Display `"-"` when null |
| `voucher_code` | str(24), nullable, FK→voucher.code | Voucher | Display as `<code>`, `"-"` when null |
| `integration_id` | str(128), nullable | Integration | Display `"-"` when null |
| `start_utc` | datetime | Start | Format: `%Y-%m-%d %H:%M` |
| `end_utc` | datetime | End | Format: `%Y-%m-%d %H:%M` |
| `grace_minutes` | — | Grace Period | Not a DB field; currently displayed in template but not on the model. Will display `"-"` |
| `created_utc` | datetime | (not shown) | Used for ordering |

**Status Computation** (applied at query time, not stored):
```
if status == REVOKED → REVOKED (preserved)
elif current_time < start_utc → PENDING
elif current_time >= end_utc → EXPIRED
else → ACTIVE
```

**Validation Rules** (from existing model):
- `mac`: max 17 chars, format AA:BB:CC:DD:EE:FF
- `booking_ref`: max 128 chars, case-sensitive
- `voucher_code`: max 24 chars, FK to voucher.code

**State Transitions** (admin-initiated via UI):
```
PENDING → REVOKED  (via revoke action)
ACTIVE  → REVOKED  (via revoke action)
EXPIRED → REVOKED  (via revoke action — idempotent-like)
ACTIVE  → ACTIVE   (via extend action — end_utc increased)
EXPIRED → ACTIVE   (via extend action — reactivated)
REVOKED → (none)   (extend and revoke buttons disabled)
```

---

### Voucher

**Table**: `voucher` | **Module**: `captive_portal.models.voucher`

| Field | Type | UI Column | Notes |
|-------|------|-----------|-------|
| `code` | str(24) (PK) | Code | Displayed as `<code>`, prominently on creation |
| `duration_minutes` | int (>0) | Duration | Display as human-readable (e.g., "60 min", "24 hrs") |
| `status` | VoucherStatus enum | Status | Raw backend status: unused, active, expired, revoked |
| `booking_ref` | str(128), nullable | Booking Ref | Display `"-"` when null |
| `created_utc` | datetime | Created | Format: `%Y-%m-%d %H:%M` |
| `redeemed_count` | int (≥0) | Redemption | Derived: "Unredeemed" if 0, "Redeemed" if >0 (FR-018) |
| `last_redeemed_utc` | datetime, nullable | (shown with Redeemed) | Only when redeemed_count > 0 |
| `expires_utc` | datetime (computed) | (not a column) | `created_utc + duration_minutes`; used for "Available Vouchers" dashboard count |

**Derived Redemption Status** (per FR-018):
```
if redeemed_count == 0 → "Unredeemed"
if redeemed_count > 0  → "Redeemed"
```

**Validation Rules** (for voucher creation form):
- `duration_minutes`: required, integer, 1–43200 (max 30 days)
- `booking_ref`: optional, max 128 chars

---

### AuditLog

**Table**: `audit_log` | **Module**: `captive_portal.models.audit_log`

| Field | Type | UI Column (Dashboard) | Notes |
|-------|------|----------------------|-------|
| `timestamp_utc` | datetime | Time | Format: `%Y-%m-%d %H:%M` |
| `action` | str(64) | Action | e.g., "grant.revoke", "voucher.create" |
| `target_type` | str(32), nullable | Target (part 1) | e.g., "grant", "voucher" |
| `target_id` | str(128), nullable | Target (part 2) | Combined: "{target_type} {target_id}" |
| `actor` | str(128) | Admin | UUID of admin; resolve to username via join |

---

### HAIntegrationConfig

**Table**: `ha_integration_config` | **Module**: `captive_portal.models.ha_integration_config`

Used only for Dashboard integrations count: `SELECT COUNT(*) FROM ha_integration_config`

---

## New View Models (not database entities)

### DashboardStats

**Purpose**: Aggregated statistics for the dashboard cards (FR-002).
**Source**: Computed by `DashboardService.get_stats()`

| Field | Type | Source Query |
|-------|------|-------------|
| `active_grants` | int | Count of grants where status ≠ REVOKED, start_utc ≤ now, end_utc > now |
| `pending_grants` | int | Count of grants where status ≠ REVOKED, start_utc > now |
| `available_vouchers` | int | Count of vouchers where status = UNUSED and Voucher.expires_utc (computed property) > now; computed in the service/ORM layer, not via an `expires_utc` DB column |
| `integrations` | int | Count of all HAIntegrationConfig rows |

### ActivityLogEntry

**Purpose**: Enriched audit log entry for dashboard display (FR-003).
**Source**: `AuditLog` joined with `AdminUser` for username resolution.

| Field | Type | Notes |
|-------|------|-------|
| `timestamp` | datetime | From `AuditLog.timestamp_utc` |
| `action` | str | From `AuditLog.action` |
| `target_type` | str | From `AuditLog.target_type` |
| `target_id` | str | From `AuditLog.target_id` |
| `admin_username` | str | Resolved from `AuditLog.actor` via AdminUser join, fallback to raw actor |

---

## Relationships Diagram

```
┌──────────────┐     ┌───────────┐     ┌──────────────────┐
│  Dashboard   │────▶│  Grants   │     │   Integrations   │
│  (stats)     │     │  (list)   │     │   (count only)   │
│              │────▶│           │     └──────────────────┘
│              │     └───────────┘              │
│              │────▶┌───────────┐              │
│              │     │ Vouchers  │              │
│  (activity)  │     │  (count)  │              │
│       │      │     └───────────┘              │
│       ▼      │                                │
│  AuditLog    │     ┌───────────┐              │
│  (recent 20) │────▶│ AdminUser │              │
│              │     │ (username)│              │
└──────────────┘     └───────────┘              │
                                                │
  AccessGrant.integration_id ──────────────────▶│
  Voucher.code ◀──── AccessGrant.voucher_code
```

No new foreign keys or relationships are added. All links are read-only queries.
