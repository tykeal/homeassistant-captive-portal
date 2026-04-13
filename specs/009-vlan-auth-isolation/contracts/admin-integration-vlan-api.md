SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: Admin Integration VLAN API

**Feature**: 009-vlan-auth-isolation
**Date**: 2025-07-14
**Component**: `captive_portal.api.routes.integrations` and `captive_portal.api.routes.vouchers`

## Overview

Extensions to the existing admin REST API for managing VLAN allowlists on integrations and vouchers. All endpoints require admin authentication via session middleware.

## Integration VLAN Endpoints

All VLAN configuration is embedded in the existing integration CRUD endpoints — no new endpoints are created.

### POST /api/integrations

**Extended request schema** (`IntegrationConfigCreate`):

```json
{
  "integration_id": "rental_control_unit_a",
  "identifier_attr": "slot_code",
  "checkout_grace_minutes": 15,
  "allowed_vlans": [50, 51]
}
```

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `allowed_vlans` | `list[int]` | No | `[]` | Each value 1–4094; duplicates removed; sorted |

**Behavior**: Creates integration with VLAN allowlist. Empty list means unrestricted.

### PATCH /api/integrations/{config_id}

**Extended request schema** (`IntegrationConfigUpdate`):

```json
{
  "allowed_vlans": [50, 55]
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `allowed_vlans` | `list[int] \| None` | No | Each value 1–4094 when provided |

**Behavior**:
- When `allowed_vlans` is provided: replaces the entire allowlist
- When `allowed_vlans` is omitted/null: no change to existing allowlist
- Setting to empty list `[]` removes all VLAN restrictions (reverts to unrestricted)
- Existing active grants are NOT affected (FR-013)

### GET /api/integrations

**Extended response schema** (`IntegrationConfigResponse`):

```json
[
  {
    "id": "uuid",
    "integration_id": "rental_control_unit_a",
    "identifier_attr": "slot_code",
    "checkout_grace_minutes": 15,
    "last_sync_utc": "2025-07-14T12:00:00Z",
    "stale_count": 0,
    "allowed_vlans": [50, 51]
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `allowed_vlans` | `list[int]` | Always present; empty list if unconfigured |

### GET /api/integrations/{config_id}

Same extended response as list endpoint, for a single integration.

---

## Voucher VLAN Endpoints

### POST /api/vouchers/

**Extended request schema** (`CreateVoucherRequest`):

```json
{
  "duration_minutes": 1440,
  "booking_ref": null,
  "code_length": 10,
  "allowed_vlans": [50, 51]
}
```

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `allowed_vlans` | `list[int] \| None` | No | `None` | Each value 1–4094; duplicates removed; sorted |

**Behavior**:
- `None` (omitted) → voucher is unrestricted (backward compatible)
- `[50, 51]` → voucher can only be redeemed from VLAN 50 or 51
- VLAN restrictions are set at creation time and cannot be changed

### GET /api/vouchers/ (list) and individual voucher responses

**Extended response schema** (`VoucherResponse`):

```json
{
  "code": "ABCD1234EF",
  "duration_minutes": 1440,
  "booking_ref": null,
  "status": "unused",
  "created_utc": "2025-07-14T12:00:00Z",
  "allowed_vlans": null
}
```

| Field | Type | Notes |
|-------|------|-------|
| `allowed_vlans` | `list[int] \| None` | `null` = unrestricted; list = restricted |

---

## Validation Error Responses

### Invalid VLAN ID in request

**Status**: 422 Unprocessable Entity

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "allowed_vlans", 0],
      "msg": "VLAN ID must be between 1 and 4094",
      "input": 5000
    }
  ]
}
```

### Non-integer VLAN value

**Status**: 422 Unprocessable Entity

```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": ["body", "allowed_vlans", 0],
      "msg": "Input should be a valid integer",
      "input": "abc"
    }
  ]
}
```

---

## Audit Trail

All VLAN configuration changes are logged via the existing `AuditService`:

| Action | `action` field | `meta` additions |
|--------|---------------|------------------|
| Create integration with VLANs | `create_integration` | `{"allowed_vlans": [50, 51]}` |
| Update integration VLANs | `update_integration` | `{"allowed_vlans_old": [50], "allowed_vlans_new": [50, 51]}` |
| Create voucher with VLANs | `voucher.create` | `{"allowed_vlans": [50, 51]}` |

---

## Invariants

1. `allowed_vlans` values are always stored deduplicated and sorted ascending.
2. An empty list `[]` and `null` are semantically equivalent for validation purposes (both = unrestricted), but `[]` is the preferred representation for integrations (explicitly "no restrictions") while `null` is preferred for vouchers (explicitly "not configured").
3. Updating `allowed_vlans` on an integration does NOT invalidate or modify existing active grants.
4. VLAN configuration endpoints require the same admin authentication level as the parent entity CRUD operations — no additional RBAC roles are needed.
