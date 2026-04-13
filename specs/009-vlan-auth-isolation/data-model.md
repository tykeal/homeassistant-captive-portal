SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: VLAN-Based Authorization Isolation

**Feature**: 009-vlan-auth-isolation
**Date**: 2025-07-14

## Entities

### 1. HAIntegrationConfig (Extended)

**Location**: `addon/src/captive_portal/models/ha_integration_config.py`
**Type**: SQLModel with `table=True` (existing, extended with new field)

| Field | Type | Default | Validation | Notes |
|-------|------|---------|------------|-------|
| `id` | `UUID` | `uuid4()` | PK | Existing |
| `integration_id` | `str` | — | Unique, max 128 | Existing |
| `identifier_attr` | `IdentifierAttr` | `SLOT_CODE` | Enum | Existing |
| `checkout_grace_minutes` | `int` | `15` | 0–30 | Existing |
| `last_sync_utc` | `datetime \| None` | `None` | — | Existing |
| `stale_count` | `int` | `0` | >= 0 | Existing |
| **`allowed_vlans`** | **`list[int] \| None`** | **`None`** | **Each int 1–4094; deduplicated; sorted** | **NEW — JSON column** |

**Business rules**:
- `allowed_vlans` is `None` or empty list `[]` → **no VLAN restriction** (all VLANs allowed, backward compatible)
- `allowed_vlans` is a non-empty list → **only devices on listed VLANs may authorize** using this integration's booking codes
- The same VLAN ID may appear on multiple integrations (FR-012 — no cross-integration uniqueness constraint)
- VLAN IDs follow IEEE 802.1Q: integers 1–4094 (FR-002)
- Changing `allowed_vlans` does NOT retroactively affect existing active grants (FR-013)

**Relationships**: Consumed by `VlanValidationService` during booking code authorization. Referenced by admin integration API and UI.

**Migration**: `ALTER TABLE ha_integration_config ADD COLUMN allowed_vlans JSON` — existing rows get `NULL` (= unrestricted).

---

### 2. Voucher (Extended)

**Location**: `addon/src/captive_portal/models/voucher.py`
**Type**: SQLModel with `table=True` (existing, extended with new field)

| Field | Type | Default | Validation | Notes |
|-------|------|---------|------------|-------|
| `code` | `str` | — | PK, 4–24 chars, A-Z0-9 | Existing |
| `duration_minutes` | `int` | — | > 0 | Existing |
| `status` | `VoucherStatus` | `UNUSED` | Enum | Existing |
| `booking_ref` | `str \| None` | `None` | Max 128 | Existing |
| `up_kbps` | `int \| None` | `None` | > 0 | Existing |
| `down_kbps` | `int \| None` | `None` | > 0 | Existing |
| `redeemed_count` | `int` | `0` | >= 0 | Existing |
| `activated_utc` | `datetime \| None` | `None` | — | Existing |
| **`allowed_vlans`** | **`list[int] \| None`** | **`None`** | **Each int 1–4094; deduplicated; sorted** | **NEW — JSON column** |

**Business rules**:
- `allowed_vlans` is `None` or empty list `[]` → **unrestricted voucher** (redeemable from any VLAN, backward compatible — FR-009)
- `allowed_vlans` is a non-empty list → **only devices on listed VLANs may redeem** (FR-008)
- VLAN restrictions are set at voucher creation time (spec assumption — no editing after creation)
- Each redemption attempt is independently validated against VLAN restrictions (spec edge case: multi-use voucher, different VLANs per attempt)

**Relationships**: Consumed by `VlanValidationService` during voucher redemption. Referenced by admin voucher API and UI.

**Migration**: `ALTER TABLE voucher ADD COLUMN allowed_vlans JSON` — existing rows get `NULL` (= unrestricted).

---

### 3. AccessGrant (Existing — No Schema Changes)

**Location**: `addon/src/captive_portal/models/access_grant.py`
**Type**: SQLModel with `table=True`

The existing `omada_vid` field stores the device's VLAN ID from the Omada redirect:

| Field | Type | Notes |
|-------|------|-------|
| `omada_vid` | `str \| None` | Max 8 chars. Already captured and stored. |
| `integration_id` | `str \| None` | Already stored for booking-based grants. |
| `voucher_code` | `str \| None` | Already stored as FK to Voucher. |
| `status` | `GrantStatus` | PENDING → ACTIVE/FAILED transitions. |

**State transitions affected by this feature**:

```
PENDING ──(VLAN validation passes)──→ [continue to controller auth] ──→ ACTIVE
PENDING ──(VLAN validation fails)──→ FAILED (denied, vlan_mismatch)
```

**No DDL changes needed** — the `omada_vid` column already exists from a prior migration.

---

### 4. VlanValidationService (New)

**Location**: `addon/src/captive_portal/services/vlan_validation_service.py`
**Type**: Service class (not a model — included here for completeness)

**Purpose**: Encapsulates all VLAN validation logic. Stateless service that takes a device VID and an entity's VLAN allowlist, and returns a validation result.

**Public interface**:

```python
class VlanValidationResult:
    """Result of VLAN validation check."""
    allowed: bool
    reason: str  # "allowed", "skipped" (no VLANs configured), "vlan_mismatch", "missing_vid"
    device_vid: int | None
    allowed_vlans: list[int]

class VlanValidationService:
    def validate_booking_vlan(
        self,
        vid_raw: str | None,
        integration: HAIntegrationConfig,
    ) -> VlanValidationResult: ...

    def validate_voucher_vlan(
        self,
        vid_raw: str | None,
        voucher: Voucher,
    ) -> VlanValidationResult: ...

    @staticmethod
    def parse_vid(vid_raw: str | None) -> int | None: ...
```

**Validation logic**:
1. If entity has no VLAN restrictions (`allowed_vlans` is `None` or `[]`) → return `allowed=True, reason="skipped"`
2. Parse `vid_raw` to integer: if missing/empty/non-numeric/out-of-range → return `allowed=False, reason="missing_vid"`
3. Check if parsed VID is in entity's `allowed_vlans` set → return `allowed=True/False, reason="allowed"/"vlan_mismatch"`

---

### 5. AuditLog (Existing — No Schema Changes)

**Location**: `addon/src/captive_portal/models/audit_log.py`
**Type**: SQLModel with `table=True`

The existing `meta` JSON column will carry additional VLAN validation data:

**New `meta` keys** (added to existing audit log entries for authorization attempts):

| Key | Type | Description |
|-----|------|-------------|
| `vlan_id` | `str \| None` | Device's raw VID from Omada redirect |
| `vlan_allowed_list` | `list[int]` | Integration/voucher's configured allowlist |
| `vlan_result` | `str` | `"allowed"`, `"skipped"`, `"vlan_mismatch"`, `"missing_vid"` |

**No DDL changes** — `meta` is already a JSON column.

---

## Database Migrations

Two new migrations will be added to `persistence/database.py`, following the established pattern of `_migrate_voucher_activated_utc()` and `_migrate_accessgrant_omada_params()`:

### Migration 1: `_migrate_integration_allowed_vlans(engine)`

```python
def _migrate_integration_allowed_vlans(engine: Engine) -> None:
    """Add allowed_vlans JSON column to ha_integration_config table."""
    insp = inspect(engine)
    if "ha_integration_config" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("ha_integration_config")}
    if "allowed_vlans" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE ha_integration_config ADD COLUMN allowed_vlans JSON"
            ))
```

### Migration 2: `_migrate_voucher_allowed_vlans(engine)`

```python
def _migrate_voucher_allowed_vlans(engine: Engine) -> None:
    """Add allowed_vlans JSON column to voucher table."""
    insp = inspect(engine)
    if "voucher" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("voucher")}
    if "allowed_vlans" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE voucher ADD COLUMN allowed_vlans JSON"
            ))
```

Both are called from `init_db()` after existing migrations.

---

## Validation Rules Summary

| Rule | Model | Field | Constraint |
|------|-------|-------|------------|
| VLAN range | Both | `allowed_vlans[*]` | Integer 1–4094 (IEEE 802.1Q) |
| Deduplication | Both | `allowed_vlans` | Duplicate VIDs silently removed |
| Sorting | Both | `allowed_vlans` | Stored in ascending order |
| Cross-integration | `HAIntegrationConfig` | `allowed_vlans` | Same VLAN may appear on multiple integrations |
| Nullable | Both | `allowed_vlans` | `None` = unrestricted (backward compatible) |
| Immutable grants | N/A | N/A | Changing VLAN config does not affect existing active grants |
