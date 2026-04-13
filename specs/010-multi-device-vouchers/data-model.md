# Data Model: Multi-Device Vouchers

**Feature Branch**: `010-multi-device-vouchers`
**Date**: 2025-07-15

## Entity Changes

### Voucher (modified)

**Table**: `voucher`

| Field | Type | Constraints | Change | Description |
|-------|------|-------------|--------|-------------|
| code | `str` | PK, 4-24 chars, A-Z0-9 | Existing | Unique voucher code |
| created_utc | `datetime` | NOT NULL, default now() | Existing | Creation timestamp (UTC) |
| duration_minutes | `int` | >0 | Existing | Grant duration in minutes |
| up_kbps | `int \| None` | >0 when set | Existing | Upload bandwidth limit |
| down_kbps | `int \| None` | >0 when set | Existing | Download bandwidth limit |
| status | `VoucherStatus` | Enum | Existing | UNUSED / ACTIVE / EXPIRED / REVOKED |
| booking_ref | `str \| None` | max 128 chars | Existing | Optional booking reference |
| redeemed_count | `int` | ≥0 | Existing | Total redemption count (audit) |
| last_redeemed_utc | `datetime \| None` | | Existing | Last redemption timestamp |
| activated_utc | `datetime \| None` | | Existing | Expiry timer start |
| allowed_vlans | `list[int] \| None` | JSON, 1-4094 | Existing | VLAN restriction list |
| **max_devices** | **`int`** | **≥1, default 1** | **NEW** | **Maximum devices allowed** |

**Validation rules**:
- `max_devices` must be a positive integer (minimum 1)
- Default value of 1 preserves backward compatibility with existing single-device behavior
- No enforced upper bound (admins trusted to set reasonable values per spec assumptions)

**Migration**:
- `ALTER TABLE voucher ADD COLUMN max_devices INTEGER DEFAULT 1`
- Existing rows automatically receive `max_devices = 1` via the DEFAULT clause
- No data backfill required
- Migration function: `_migrate_voucher_max_devices()` in `database.py`

### AccessGrant (unchanged)

**Table**: `accessgrant`

No schema changes needed. The existing `AccessGrant` model already has:
- `voucher_code` (FK to `voucher.code`) — links grants to vouchers
- `mac` (indexed) — device identifier
- `status` (GrantStatus enum) — PENDING / ACTIVE / EXPIRED / REVOKED / FAILED

The multi-device feature leverages the existing one-to-many relationship between Voucher and AccessGrant. Device capacity is enforced by counting active grants per voucher at redemption time.

## Relationships

```text
┌──────────────────┐         ┌──────────────────────┐
│     Voucher      │ 1   0..N│    AccessGrant       │
│──────────────────│─────────│──────────────────────│
│ code (PK)        │         │ id (PK, UUID)        │
│ max_devices      │         │ voucher_code (FK)    │
│ duration_minutes │         │ mac                  │
│ status           │         │ device_id            │
│ redeemed_count   │         │ status               │
│ ...              │         │ ...                  │
└──────────────────┘         └──────────────────────┘

Capacity rule:
  COUNT(accessgrant WHERE voucher_code = V.code
        AND status IN ('pending', 'active')) < V.max_devices
  → redemption allowed
```

## State Transitions

### Voucher Status (unchanged)

```text
                  ┌────────────┐
                  │   UNUSED   │
                  └─────┬──────┘
                        │ first redemption
                        ▼
                  ┌────────────┐
        ┌─────── │   ACTIVE   │ ◄── subsequent redemptions (no status change)
        │         └─────┬──────┘
        │               │ time expires
        │               ▼
        │         ┌────────────┐
        │         │  EXPIRED   │
        │         └────────────┘
        │
        │ admin revoke (from any non-expired state)
        ▼
  ┌────────────┐
  │  REVOKED   │
  └────────────┘
```

Note: There is no "FULLY_REDEEMED" status. Device capacity is enforced dynamically by counting active grants, not by voucher status. This means:
- A voucher with `max_devices=3` and 3 active grants stays `ACTIVE`
- If one grant is revoked, the voucher still stays `ACTIVE` and can accept a new device
- Status only changes via expiration or admin revocation

### Redemption Decision Flow

```text
  Guest submits voucher code + MAC
         │
         ▼
  ┌─ Voucher exists? ──── No ──→ Error: "Voucher not found"
  │       │
  │      Yes
  │       ▼
  ├─ Voucher revoked? ─── Yes ──→ Error: "Voucher revoked"
  │       │
  │      No
  │       ▼
  ├─ Voucher expired? ─── Yes ──→ Error: "Voucher expired"
  │       │
  │      No
  │       ▼
  ├─ MAC already has ──── Yes ──→ Error: "Device already authorized"
  │  active grant for             (FR-008: don't consume slot)
  │  this voucher?
  │       │
  │      No
  │       ▼
  ├─ Active grant ─────── Yes ──→ Error: "Voucher device limit reached"
  │  count >= max_devices?        (FR-005)
  │       │
  │      No
  │       ▼
  └─ Create grant ─────────────→ Success: device authorized
     Increment redeemed_count
     Set activated_utc (if first use)
```

## New Repository Methods

### `AccessGrantRepository.count_active_by_voucher_code(voucher_code: str) -> int`

Returns the count of non-revoked, non-failed grants for a voucher code.

```sql
SELECT COUNT(*)
FROM accessgrant
WHERE voucher_code = :code
  AND status IN ('pending', 'active')
```

### `AccessGrantRepository.count_active_by_voucher_codes(codes: list[str]) -> dict[str, int]`

Batch query for the admin voucher list page. Returns a mapping of voucher code → active grant count.

```sql
SELECT voucher_code, COUNT(*) as cnt
FROM accessgrant
WHERE voucher_code IN (:codes)
  AND status IN ('pending', 'active')
GROUP BY voucher_code
```

## API Request/Response Changes

### CreateVoucherRequest (modified)

```python
class CreateVoucherRequest(BaseModel):
    duration_minutes: int = Field(gt=0, le=43200)
    booking_ref: str | None = Field(default=None, max_length=128)
    up_kbps: int | None = Field(default=None, gt=0)
    down_kbps: int | None = Field(default=None, gt=0)
    code_length: int = Field(default=10, ge=4, le=24)
    allowed_vlans: list[int] | None = Field(default=None)
    max_devices: int = Field(default=1, ge=1)  # NEW
```

### VoucherResponse (modified)

```python
class VoucherResponse(BaseModel):
    code: str
    duration_minutes: int
    booking_ref: str | None
    up_kbps: int | None
    down_kbps: int | None
    status: str
    created_utc: datetime
    allowed_vlans: list[int] | None = None
    max_devices: int  # NEW
    active_devices: int  # NEW - computed from grant count
```
