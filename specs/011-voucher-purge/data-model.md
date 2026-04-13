# Data Model: Voucher Auto-Purge and Admin Purge

**Feature Branch**: `011-voucher-purge`
**Date**: 2025-07-22

## Entity Changes

### Voucher (modified)

**Table**: `voucher`

| Field | Type | Nullable | Default | Description |
|-------|------|----------|---------|-------------|
| `code` | `str` (PK) | No | — | Voucher code (A-Z0-9, 4-24 chars) |
| `created_utc` | `datetime` | No | `now(UTC)` | Creation timestamp |
| `duration_minutes` | `int` | No | — | Grant duration in minutes |
| `status` | `VoucherStatus` | No | `UNUSED` | Lifecycle status |
| `activated_utc` | `datetime` | Yes | `None` | When expiry timer started |
| `last_redeemed_utc` | `datetime` | Yes | `None` | Last redemption timestamp |
| `redeemed_count` | `int` | No | `0` | Number of redemptions |
| `booking_ref` | `str` | Yes | `None` | Optional booking reference |
| `allowed_vlans` | `list[int]` (JSON) | Yes | `None` | VLAN restrictions |
| `max_devices` | `int` | No | `1` | Max simultaneous devices |
| `up_kbps` | `int` | Yes | `None` | Upload bandwidth limit |
| `down_kbps` | `int` | Yes | `None` | Download bandwidth limit |
| **`status_changed_utc`** | **`datetime`** | **Yes** | **`None`** | **NEW: When voucher entered its current terminal status (EXPIRED or REVOKED). NULL for UNUSED/ACTIVE vouchers.** |

**New field details**:
- `status_changed_utc: Optional[datetime] = Field(default=None)` added to the SQLModel class
- Set to `datetime.now(timezone.utc)` whenever status transitions to `EXPIRED` or `REVOKED`
- NOT overwritten if voucher is already in a terminal status (idempotent protection)
- Used as the age reference for purge eligibility calculations

### VoucherStatus Enum (unchanged)

```python
class VoucherStatus(str, Enum):
    UNUSED = "unused"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
```

### AccessGrant (unchanged, affected by purge)

**Table**: `accessgrant`

| Relevant Field | Type | Nullable | Description |
|---------------|------|----------|-------------|
| `voucher_code` | `str` (FK→voucher.code) | Yes | Reference to source voucher. **Set to NULL when the referenced voucher is purged.** |

No schema changes to AccessGrant. The existing nullable FK already supports the nullification behavior required by FR-011.

### AuditLog (unchanged, new entries added)

**Table**: `auditlog`

No schema changes. New purge operations create audit entries using existing fields:

| Field | Auto-purge value | Manual purge value |
|-------|-----------------|-------------------|
| `actor` | `"system"` | Admin username (from session) |
| `action` | `"voucher.auto_purge"` | `"voucher.manual_purge"` |
| `target_type` | `"voucher"` | `"voucher"` |
| `target_id` | `None` | `None` |
| `outcome` | `"success"` | `"success"` |
| `meta` | `{"purged_count": N, "retention_days": 30, "cutoff_utc": "..."}` | `{"purged_count": N, "min_age_days": N, "cutoff_utc": "..."}` |

## State Transitions

### Voucher Status Lifecycle (updated)

```
                     ┌──────────────────────────────────────────────┐
                     │                                              │
  ┌────────┐   redeem   ┌────────┐   expire    ┌─────────┐   purge (≥30d)   ┌─────────┐
  │ UNUSED │ ──────────→ │ ACTIVE │ ──────────→ │ EXPIRED │ ──────────────→ │ DELETED │
  └────────┘             └────────┘             └─────────┘                 └─────────┘
       │                      │                      ↑                          ↑
       │     revoke           │     revoke           │                          │
       └──────────────────────┴──────────→ ┌─────────┐   purge (≥30d)          │
                                           │ REVOKED │ ────────────────────────┘
                                           └─────────┘
```

**Transition rules for `status_changed_utc`**:
1. UNUSED → ACTIVE: `status_changed_utc` remains NULL (not a terminal status)
2. ACTIVE → EXPIRED: `status_changed_utc = now(UTC)`
3. UNUSED → REVOKED: `status_changed_utc = now(UTC)`
4. ACTIVE → REVOKED: `status_changed_utc = now(UTC)`
5. EXPIRED (re-processed): `status_changed_utc` NOT overwritten (idempotent)
6. REVOKED (re-processed): `status_changed_utc` NOT overwritten (idempotent)

### Purge Eligibility Rules

A voucher is eligible for purge when ALL conditions are met:
1. `status` is `EXPIRED` or `REVOKED`
2. `status_changed_utc` is not NULL
3. One of the following age rules applies:
   - **Auto-purge**: `status_changed_utc < (now - 30 days)`
   - **Manual purge, N > 0**: `status_changed_utc < (now - N days)`
   - **Manual purge, N = 0**: no age/cutoff check is applied;
     all terminal vouchers with non-NULL `status_changed_utc`
     are eligible

This special-case for manual purge with `N=0` is normative and
overrides the retention-period comparison.

## Migration Specification

### `_migrate_voucher_status_changed_utc(engine)`

Added to `init_db()` after `_migrate_voucher_max_devices()`.

**Steps**:
1. Inspect `voucher` table columns
2. If `status_changed_utc` not present:
   - `ALTER TABLE voucher ADD COLUMN status_changed_utc DATETIME`
3. Backfill EXPIRED vouchers:
   ```sql
   UPDATE voucher
   SET status_changed_utc = datetime(
     activated_utc, '+' || duration_minutes || ' minutes'
   )
   WHERE status = 'expired'
   AND status_changed_utc IS NULL
   AND activated_utc IS NOT NULL
   ```
   Fallback for EXPIRED vouchers without `activated_utc`:
   ```sql
   UPDATE voucher
   SET status_changed_utc = datetime(
     created_utc, '+' || duration_minutes || ' minutes'
   )
   WHERE status = 'expired'
   AND status_changed_utc IS NULL
   AND activated_utc IS NULL
   ```
4. Backfill REVOKED vouchers:
   ```sql
   UPDATE voucher
   SET status_changed_utc = :migration_time
   WHERE status = 'revoked'
   AND status_changed_utc IS NULL
   ```
   Where `:migration_time` is `datetime.now(timezone.utc)` captured at the start of the migration function.

## New Repository Methods

### VoucherRepository additions

```python
def count_purgeable(self, cutoff: datetime) -> int:
    """Count vouchers eligible for purge (EXPIRED/REVOKED with status_changed_utc < cutoff).

    Args:
        cutoff: Cutoff datetime; vouchers with status_changed_utc before this are eligible.

    Returns:
        Count of purgeable vouchers.
    """

def get_purgeable_codes(self, cutoff: datetime) -> list[str]:
    """Return codes of vouchers eligible for purge.

    Retrieves the codes of all vouchers in EXPIRED or REVOKED
    status whose status_changed_utc is before the given cutoff.
    Used to identify grant references that must be nullified
    before purge deletion.

    Args:
        cutoff: Cutoff datetime.

    Returns:
        List of voucher codes eligible for purge.
    """

def purge(self, cutoff: datetime) -> int:
    """Delete vouchers eligible for purge.

    Deletes all vouchers in EXPIRED or REVOKED status whose
    status_changed_utc is before the given cutoff.

    Args:
        cutoff: Cutoff datetime.

    Returns:
        Number of deleted vouchers.
    """
```

### AccessGrantRepository additions

```python
def nullify_voucher_references(self, voucher_codes: list[str]) -> int:
    """Set voucher_code to NULL for grants referencing the given voucher codes.

    Args:
        voucher_codes: List of voucher codes being purged.

    Returns:
        Number of grant records updated.
    """
```

## New Service

### VoucherPurgeService

```python
class VoucherPurgeService:
    """Service for purging expired and revoked vouchers.

    Handles both automatic (retention-based) and manual (admin-initiated)
    purge operations, including grant reference cleanup and audit logging.

    Attributes:
        voucher_repo: Voucher repository
        grant_repo: Access grant repository
        audit_service: Audit logging service
        retention_days: Default retention period for auto-purge (30 days)
    """

    def __init__(
        self,
        voucher_repo: VoucherRepository,
        grant_repo: AccessGrantRepository,
        audit_service: AuditService,
        retention_days: int = 30,
    ) -> None: ...

    async def auto_purge(self) -> int:
        """Run automatic purge of vouchers past the retention period.

        Returns:
            Number of vouchers purged.
        """

    async def count_purgeable(self, min_age_days: int) -> int:
        """Count vouchers eligible for manual purge with given age threshold.

        Args:
            min_age_days: Minimum age in days. 0 means all terminal vouchers.

        Returns:
            Count of eligible vouchers.
        """

    async def manual_purge(self, min_age_days: int, actor: str) -> int:
        """Execute admin-initiated purge.

        Args:
            min_age_days: Minimum age in days. 0 means all terminal vouchers.
            actor: Admin username for audit trail.

        Returns:
            Number of vouchers purged.
        """
```

## Validation Rules

### Manual Purge Input

| Field | Type | Validation | Error Message |
|-------|------|------------|---------------|
| `min_age_days` | `int` | Non-negative integer (≥0) | "Age threshold must be a non-negative integer." |
| `csrf_token` | `str` | Valid CSRF token | Standard CSRF error |
