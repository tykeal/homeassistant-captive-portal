# API Contract Changes: Multi-Device Vouchers

**Feature Branch**: `010-multi-device-vouchers`
**Date**: 2025-07-15

## Admin API

### POST `/api/vouchers/` — Create Voucher

**Change**: Add `max_devices` field to request body.

**Request body** (JSON):
```json
{
  "duration_minutes": 1440,
  "booking_ref": "BOOKING-001",
  "up_kbps": null,
  "down_kbps": null,
  "code_length": 10,
  "allowed_vlans": null,
  "max_devices": 5
}
```

| Field | Type | Required | Default | Constraints | Change |
|-------|------|----------|---------|-------------|--------|
| `duration_minutes` | int | Yes | — | 1-43200 | Existing |
| `booking_ref` | string\|null | No | null | max 128 chars | Existing |
| `up_kbps` | int\|null | No | null | >0 | Existing |
| `down_kbps` | int\|null | No | null | >0 | Existing |
| `code_length` | int | No | 10 | 4-24 | Existing |
| `allowed_vlans` | int[]\|null | No | null | 1-4094 | Existing |
| **`max_devices`** | **int** | **No** | **1** | **≥1** | **NEW** |

**Response body** (201 Created):
```json
{
  "code": "AB12CD34EF",
  "duration_minutes": 1440,
  "booking_ref": "BOOKING-001",
  "up_kbps": null,
  "down_kbps": null,
  "status": "unused",
  "created_utc": "2025-07-15T10:30:00Z",
  "allowed_vlans": null,
  "max_devices": 5,
  "active_devices": 0
}
```

**Backward compatibility**: The `max_devices` field defaults to `1` when omitted. Existing clients that do not send `max_devices` will continue to create single-device vouchers unchanged.

**Error responses** (unchanged):
- `400 Bad Request`: Invalid parameters (includes `max_devices < 1`)
- `409 Conflict`: Voucher code collision

---

### GET `/admin/vouchers/` — Voucher List Page (HTML)

**Change**: The template context now includes device usage data.

**New template context variables**:
| Variable | Type | Description |
|----------|------|-------------|
| `voucher_device_counts` | `dict[str, int]` | Map of voucher code → count of active (non-revoked) grants |

**Table column changes**:
- Existing "Redemption" column replaced with "Devices" column
- For `max_devices = 1`: Display "Redeemed" / "Unredeemed" (backward-compatible)
- For `max_devices > 1`: Display "N/M devices" (e.g., "2/5 devices")

---

### POST `/admin/vouchers/create` — Create Voucher (HTML form)

**Change**: Form now accepts `max_devices` field.

**New form field**:
| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `max_devices` | number input | 1 | min=1 | Maximum devices per voucher |

---

### POST `/admin/vouchers/bulk-create` — Bulk Create Vouchers (NEW)

**New endpoint** for creating multiple vouchers at once.

**Request** (form POST):
| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `csrf_token` | hidden | Yes | — | CSRF token |
| `count` | int | Yes | — | 1-100 |
| `duration_minutes` | int | Yes | — | 1-43200 |
| `max_devices` | int | No | 1 | ≥1 |
| `booking_ref` | string | No | — | max 128 chars |
| `allowed_vlans` | string | No | — | Comma-separated VLAN IDs |

**Response**: 303 redirect to `/admin/vouchers/` with success/error message.

**Success message example**: `"Created 10 vouchers successfully"`

---

## Guest Portal

### POST `/authorize` — Guest Authorization

**No API changes**. The authorization endpoint is unchanged.

**Behavioral changes** (same endpoint, different error messages):
- When a multi-device voucher has reached its device limit, the error detail changes from `"Voucher '{code}' already redeemed for MAC '{mac}'"` to a capacity-specific message.
- New error message for device limit reached: `"This code has reached its maximum number of devices."`
- Existing error for duplicate device unchanged in behavior but updated message: `"Your device is already authorized with this code."`

**Error response mapping**:
| Scenario | HTTP Status | Detail (current) | Detail (new) |
|----------|------------|-------------------|--------------|
| Device already authorized for this voucher | 410 Gone | `Voucher '{code}' already redeemed for MAC '{mac}'` | `Your device is already authorized with this code.` |
| Device limit reached | 410 Gone | N/A (new scenario) | `This code has reached its maximum number of devices.` |
| Voucher not found | 410 Gone | `Voucher code '{code}' not found` | Unchanged |
| Voucher revoked | 410 Gone | `Voucher '{code}' has been revoked` | Unchanged |
| Voucher expired | 410 Gone | `Voucher '{code}' expired at {time}` | Unchanged |

---

## Internal Service Contract

### `VoucherService.create()` — Signature Change

```python
async def create(
    self,
    duration_minutes: int,
    booking_ref: Optional[str] = None,
    up_kbps: Optional[int] = None,
    down_kbps: Optional[int] = None,
    code_length: int = 10,
    max_retries: int = 5,
    allowed_vlans: list[int] | None = None,
    max_devices: int = 1,  # NEW parameter
) -> Voucher:
```

### `VoucherService.redeem()` — Behavioral Change

No signature change. Internal logic modified to:
1. After duplicate MAC check, count active grants for the voucher
2. If `active_grant_count >= voucher.max_devices`, raise `VoucherRedemptionError`
3. Otherwise, proceed with grant creation as today

### New Exception Variant

```python
class VoucherDeviceLimitError(VoucherRedemptionError):
    """Raised when voucher has reached its maximum device count."""
    def __init__(self, code: str, max_devices: int) -> None: ...
```

This subclass allows the guest portal route to distinguish between "voucher fully redeemed" and other redemption errors for appropriate messaging, while remaining backward-compatible with existing `except VoucherRedemptionError` handlers.
