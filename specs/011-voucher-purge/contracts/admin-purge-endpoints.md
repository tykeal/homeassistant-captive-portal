# Contracts: Voucher Auto-Purge and Admin Purge

**Feature Branch**: `011-voucher-purge`
**Date**: 2025-07-22

## Overview

The voucher purge feature is entirely admin-facing (server-rendered HTML UI) and does not introduce new external API endpoints. The existing REST API (`POST /api/vouchers/`) is unaffected. No public API contract changes are required.

## Internal Contracts

### Admin UI Endpoints (HTML, server-rendered)

These endpoints are internal to the admin interface and follow the existing Post/Redirect/Get pattern. They are not versioned REST APIs — they render HTML responses and redirect.

#### POST `/admin/vouchers/purge-preview`

**Purpose**: Calculate and display the count of vouchers eligible for purge.

**Form Parameters**:
| Parameter | Type | Required | Validation |
|-----------|------|----------|------------|
| `csrf_token` | `string` | Yes | Valid CSRF token |
| `min_age_days` | `string` (form field) | Yes | Must parse to non-negative integer (≥0) |

**Response**: `303 See Other` redirect to `/admin/vouchers/?purge_preview_count=N&purge_preview_days=D`

**Error Response**: `303 See Other` redirect to `/admin/vouchers/?error=<message>` for invalid input.

---

#### POST `/admin/vouchers/purge-confirm`

**Purpose**: Execute the purge of eligible vouchers.

**Form Parameters**:
| Parameter | Type | Required | Validation |
|-----------|------|----------|------------|
| `csrf_token` | `string` | Yes | Valid CSRF token |
| `min_age_days` | `string` (form field) | Yes | Must parse to non-negative integer (≥0) |

**Response**: `303 See Other` redirect to `/admin/vouchers/?success=Purged+N+vouchers`

**Side Effects**:
- Deletes eligible vouchers from the database
- Sets `voucher_code = NULL` on associated access grants
- Creates an audit log entry with action `voucher.manual_purge`

---

### Audit Log Actions (internal)

New audit actions introduced by this feature:

| Action | Actor | When |
|--------|-------|------|
| `voucher.auto_purge` | `system` | Auto-purge runs on admin page load |
| `voucher.manual_purge` | Admin username | Admin confirms manual purge |

### Database Schema Change

One new nullable column added to the `voucher` table:

```sql
ALTER TABLE voucher ADD COLUMN status_changed_utc DATETIME;
```

This is an additive, backward-compatible change. Existing rows receive backfilled values during migration. Application code handles NULL values gracefully (vouchers without `status_changed_utc` are not eligible for purge until the migration runs).
