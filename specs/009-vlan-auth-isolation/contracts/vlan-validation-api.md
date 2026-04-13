SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: VLAN Validation Service

**Feature**: 009-vlan-auth-isolation
**Date**: 2025-07-14
**Component**: `captive_portal.services.vlan_validation_service`

## Overview

The `VlanValidationService` is a stateless service that determines whether a device's VLAN ID is authorized for a given integration or voucher. It is the single enforcement point for all VLAN isolation logic.

## Public Interface

### `VlanValidationResult`

```python
class VlanValidationResult:
    """Immutable result of a VLAN validation check.

    Attributes:
        allowed: Whether the device is permitted to authorize.
        reason: Machine-readable reason code.
        device_vid: Parsed device VLAN ID (None if unparseable).
        allowed_vlans: The entity's configured VLAN allowlist.
    """
    allowed: bool
    reason: str       # "allowed" | "skipped" | "vlan_mismatch" | "missing_vid"
    device_vid: int | None
    allowed_vlans: list[int]
```

### `VlanValidationService.validate_booking_vlan`

```python
def validate_booking_vlan(
    self,
    vid_raw: str | None,
    integration: HAIntegrationConfig,
) -> VlanValidationResult:
    """Validate device VLAN against an integration's allowlist.

    Args:
        vid_raw: Raw VID string from Omada controller redirect.
        integration: The integration whose booking event matched.

    Returns:
        VlanValidationResult with allowed=True/False and reason.
    """
```

**Behavior**:

| `integration.allowed_vlans` | `vid_raw` | Result |
|-----------------------------|-----------|--------|
| `None` or `[]` | any | `allowed=True, reason="skipped"` |
| `[50, 51]` | `"50"` | `allowed=True, reason="allowed"` |
| `[50, 51]` | `"52"` | `allowed=False, reason="vlan_mismatch"` |
| `[50, 51]` | `None` | `allowed=False, reason="missing_vid"` |
| `[50, 51]` | `""` | `allowed=False, reason="missing_vid"` |
| `[50, 51]` | `"abc"` | `allowed=False, reason="missing_vid"` |
| `[50, 51]` | `"-1"` | `allowed=False, reason="missing_vid"` |
| `[50, 51]` | `"4095"` | `allowed=False, reason="missing_vid"` |

### `VlanValidationService.validate_voucher_vlan`

```python
def validate_voucher_vlan(
    self,
    vid_raw: str | None,
    voucher: Voucher,
) -> VlanValidationResult:
    """Validate device VLAN against a voucher's allowlist.

    Args:
        vid_raw: Raw VID string from Omada controller redirect.
        voucher: The voucher being redeemed.

    Returns:
        VlanValidationResult with allowed=True/False and reason.
    """
```

**Behavior**: Identical to `validate_booking_vlan` but reads `voucher.allowed_vlans` instead of `integration.allowed_vlans`.

### `VlanValidationService.parse_vid`

```python
@staticmethod
def parse_vid(vid_raw: str | None) -> int | None:
    """Parse and validate a raw VID string.

    Args:
        vid_raw: Raw VID from Omada redirect. May be None, empty,
                 non-numeric, or out of IEEE 802.1Q range.

    Returns:
        Integer VLAN ID (1-4094) or None if invalid/missing.
    """
```

**Behavior**:
- `None` → `None`
- `""` → `None`
- `"  "` (whitespace) → `None`
- `"50"` → `50`
- `"abc"` → `None`
- `"0"` → `None` (below range)
- `"4095"` → `None` (above range)
- `"-1"` → `None` (below range)
- `"50.5"` → `None` (non-integer)

## Error Messages

The service itself does not generate user-facing error messages. The calling route is responsible for mapping `VlanValidationResult.reason` to the appropriate HTTP error:

| Reason | HTTP Status | User Message |
|--------|-------------|--------------|
| `vlan_mismatch` | 403 | "This code is not valid for your network." |
| `missing_vid` | 403 | "Unable to identify your network. Please check your connection and try again." |
| `skipped` | N/A | No error — continue authorization |
| `allowed` | N/A | No error — continue authorization |

## Invariants

1. VLAN validation is **never** performed when `allowed_vlans` is `None` or `[]` — the service returns immediately with `reason="skipped"`.
2. The service does **not** modify any database state — it is purely a validation check.
3. The service is stateless — it can be instantiated per-request or shared.
4. VID parsing is strict: only exact integer strings in range 1–4094 are accepted.
