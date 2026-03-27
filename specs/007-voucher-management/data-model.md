SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Voucher Management

**Feature**: 007-voucher-management | **Date**: 2025-07-18

This feature does not introduce new database entities. It adds lifecycle management operations (revoke, delete, bulk) to the existing Voucher model and extends the service and repository layers. This document maps existing entities to the new requirements and identifies new service interfaces, error types, and view models.

## Existing Entity (no schema changes)

### Voucher

**Table**: `voucher` | **Module**: `captive_portal.models.voucher`

| Field | Type | Revoke/Delete Relevance | Notes |
|-------|------|------------------------|-------|
| `code` | str(24) (PK) | URL path parameter & form field | Used in POST action URLs and checkbox values |
| `created_utc` | datetime | Used in `expires_utc` computation | No direct use in revoke/delete logic |
| `duration_minutes` | int (>0) | Used in `expires_utc` computation | No direct use in revoke/delete logic |
| `status` | VoucherStatus enum | Revoke target field; eligibility check | Set to REVOKED on revoke; checked for revoke/delete eligibility |
| `booking_ref` | str(128), nullable | Captured in delete audit meta | Preserved in audit log before hard delete |
| `redeemed_count` | int (≥0) | Delete eligibility guard | Delete only permitted when `redeemed_count == 0` |
| `last_redeemed_utc` | datetime, nullable | Not directly used | Informational display only |
| `up_kbps` | int, nullable | Not used | No impact on management actions |
| `down_kbps` | int, nullable | Not used | No impact on management actions |
| `expires_utc` | datetime (computed) | Revoke eligibility check | `now <= expires_utc` required for revoke |

**VoucherStatus Enum** (existing, no changes):
```
UNUSED   = "unused"
ACTIVE   = "active"
EXPIRED  = "expired"
REVOKED  = "revoked"
```

**State Transitions** (admin-initiated via this feature):
```
UNUSED  → REVOKED  (revoke action, if not expired)
ACTIVE  → REVOKED  (revoke action, if not expired)
REVOKED → REVOKED  (no-op, idempotent)
EXPIRED → (revoke rejected — not eligible)

UNUSED  → (deleted) (delete action, redeemed_count == 0)
REVOKED → (deleted) (delete action, redeemed_count == 0, FR-009)
ACTIVE  → (delete rejected — redeemed_count > 0)
```

**Revoke Eligibility** (per FR-001, FR-005):
```
eligible = (
    status in {UNUSED, ACTIVE}
    AND now <= expires_utc
)
OR status == REVOKED  # idempotent no-op
```

**Delete Eligibility** (per FR-006, FR-008, FR-009):
```
eligible = redeemed_count == 0
```

**Validation Rules** (applied in VoucherService):
- Revoke: voucher must exist, must not be expired (`now > expires_utc` → VoucherExpiredError)
- Delete: voucher must exist, `redeemed_count` must be 0 (else → VoucherRedeemedError)
- Delete race condition (FR-010): perform atomic `DELETE ... WHERE code = :code AND redeemed_count = 0` and verify affected rowcount

---

## Existing Entity (no changes, referenced for context)

### AuditLog

**Table**: `audit_log` | **Module**: `captive_portal.models.audit_log`

New action types added by this feature:

| Action | target_type | target_id | meta |
|--------|-------------|-----------|------|
| `voucher.revoke` | `"voucher"` | voucher code | `{}` |
| `voucher.delete` | `"voucher"` | voucher code | `{"status_at_delete": "unused", "booking_ref": "REF-123"}` |

Delete actions capture voucher state in meta because the record is hard-deleted afterward.

---

## New Error Types

**Module**: `captive_portal.services.voucher_service` (alongside existing VoucherService)

| Error Class | Raised When | Used By |
|------------|-------------|---------|
| `VoucherNotFoundError` | `VoucherRepository.get_by_code()` returns None | `revoke()`, `delete()` |
| `VoucherExpiredError` | `now > voucher.expires_utc` on revoke attempt | `revoke()` |
| `VoucherRedeemedError` | `voucher.redeemed_count > 0` on delete attempt | `delete()` |

These follow the existing `GrantNotFoundError` / `GrantOperationError` pattern from `grant_service.py`.

---

## New Repository Method

**Class**: `VoucherRepository` in `captive_portal.persistence.repositories`

| Method | Signature | Description |
|--------|-----------|-------------|
| `delete` | `delete(self, code: str) -> bool` | Remove voucher row by PK if it has never been redeemed. Returns True if deleted, False if not found or already redeemed. |

Implementation:
```python
from sqlalchemy import delete

def delete(self, code: str) -> bool:
    """Hard-delete a voucher that has never been redeemed.

    Returns:
        True if a single voucher row was deleted.
        False if no such voucher exists or it has already been redeemed.
    """
    stmt = (
        delete(Voucher)
        .where(
            Voucher.code == code,
            Voucher.redeemed_count == 0,
        )
    )
    result = self.session.execute(stmt)
    deleted = result.rowcount == 1
    if deleted:
        self.session.flush()
    return deleted
```

---

## New Service Methods

**Class**: `VoucherService` in `captive_portal.services.voucher_service`

| Method | Signature | Description |
|--------|-----------|-------------|
| `revoke` | `async revoke(self, code: str) -> Voucher` | Revoke voucher (idempotent). Raises VoucherNotFoundError, VoucherExpiredError. |
| `delete` | `async delete(self, code: str) -> None` | Hard-delete voucher. Raises VoucherNotFoundError, VoucherRedeemedError. |

---

## New View Model

### VoucherActions

**Purpose**: Pre-computed action eligibility for each voucher at render time.
**Source**: Computed in the GET `/admin/vouchers/` route handler.

| Field | Type | Computation |
|-------|------|-------------|
| `can_revoke` | bool | `status not in {REVOKED, EXPIRED} and now <= expires_utc` |
| `can_delete` | bool | `redeemed_count == 0` |

Passed to the template as a `dict[str, VoucherActions]` keyed by voucher code, similar to `grant_statuses` on the grants page.

### BulkResult

**Purpose**: Summary of a bulk operation outcome for feedback message generation.
**Source**: Constructed in bulk route handlers.

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | `"revoked"` or `"deleted"` |
| `success_count` | int | Number of vouchers successfully processed |
| `skip_reasons` | dict[str, int] | Skip reason → count (e.g., `{"expired": 2}`) |

---

## Relationships Diagram

```
┌─────────────────────┐
│     Voucher          │
│  (existing table)    │
│                      │     ┌──────────────────┐
│  code (PK)          │     │   AuditLog        │
│  status             │────▶│  (existing table)  │
│  redeemed_count     │     │                    │
│  expires_utc (comp) │     │  voucher.revoke    │
│  booking_ref        │     │  voucher.delete    │
└─────────────────────┘     │  voucher.create    │
        │                   └──────────────────┘
        │
        ▼
┌─────────────────────┐
│  VoucherService      │
│  (modified)          │
│                      │
│  + revoke(code)      │
│  + delete(code)      │
│  create(...)  [existing]│
│  redeem(...)  [existing]│
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ VoucherRepository    │
│  (modified)          │
│                      │
│  + delete(code)      │
│  get_by_code [existing]│
└─────────────────────┘
```

No new foreign keys, tables, or relationships are added. All changes extend existing classes.
