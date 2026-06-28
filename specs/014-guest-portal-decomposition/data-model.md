SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Guest Portal Decomposition

**Feature**: 014-guest-portal-decomposition
**Date**: 2026-06-28

## Schema Decision

No persistent schema changes are planned or allowed. Existing SQLModel tables,
columns, defaults, and migrations remain unchanged. The decomposition introduces
only internal typed values used to pass current request state between smaller
helper functions.

## Existing Persistent Entities

### 1. AccessGrant (Unchanged)

**Location**: `addon/src/captive_portal/models/access_grant.py`
**Type**: SQLModel table

| Field/Behavior | Preservation requirement |
|----------------|--------------------------|
| `mac` / `device_id` | Continue storing the normalized MAC address used for authorization |
| `booking_ref` | Preserve case-sensitive booking identifier from the matched event |
| `user_input_code` | Preserve the guest's original booking input value |
| `integration_id` | Preserve the matched rental-control integration ID |
| `start_utc` / `end_utc` | Preserve voucher duration and booking window/grace rounding behavior |
| `status` | Preserve PENDING, ACTIVE, FAILED and related transitions |
| `controller_grant_id` | Preserve adapter `grant_id` storage on controller success |
| `omada_gateway_mac` | Preserve stripped/truncated gateway MAC metadata |
| `omada_ap_mac` | Preserve stripped/truncated AP MAC metadata |
| `omada_vid` | Preserve stripped/truncated VLAN ID metadata |
| `omada_ssid_name` | Preserve stripped/truncated SSID metadata |
| `omada_radio_id` | Preserve stripped/truncated radio ID metadata |

### 2. Voucher (Unchanged)

**Location**: `addon/src/captive_portal/models/voucher.py`
**Type**: SQLModel table

Voucher validation, redemption, expiry, revocation, device limit, duplicate
device behavior, status updates, and VLAN allowlist behavior remain owned by
existing services and models. The refactor only moves route orchestration around
those calls.

### 3. HAIntegrationConfig and RentalControlEvent (Unchanged)

**Locations**:

- `addon/src/captive_portal/models/ha_integration_config.py`
- `addon/src/captive_portal/models/rental_control_event.py`

Booking lookup across all configured integrations, identifier attribute use,
checkout grace minutes, booking windows, duplicate grant checks, VLAN allowlist
checks, and missing-integration errors are preserved.

### 4. PortalConfig (Unchanged)

**Location**: `addon/src/captive_portal/models/portal_config.py`

Trusted proxy network handling, redirect validation configuration, and portal
security behavior remain unchanged. No settings or UI fields are added.

## Internal Values Introduced by the Refactor

These are implementation-only data carriers. They must not change database
schema, HTTP request fields, response models, or operator configuration.

### 1. GuestOmadaParams

**Purpose**: Group Omada metadata currently passed between route handlers,
helpers, hidden fields, retry URLs, grant metadata, and controller payloads.

| Attribute | Source field | Existing destination |
|-----------|--------------|----------------------|
| `client_mac` | `clientMac` query or `client_mac` form | MAC extraction and retry URL |
| `client_ip` | `clientIp` query | Hidden form field/debug context |
| `site` | `site` query/form | Retry URL and legacy site override |
| `gateway_mac` | `gatewayMac` query or `gateway_mac` form | Grant metadata and controller authorize |
| `ap_mac` | `apMac` query or `ap_mac` form | Grant metadata and controller authorize |
| `radio_id` | `radioId` query or `radio_id` form | Grant metadata and controller authorize |
| `ssid_name` | `ssidName` query or `ssid_name` form | Grant metadata and controller authorize |
| `vid` | `vid` query/form | VLAN check, grant metadata, controller authorize |
| `t` | `t` query | Hidden form field only |
| `redirect_url` | `redirectUrl` query | Effective continue fallback |
| `continue_url` | `continue` query or `continue_url` form | Safe success redirect |

**Business rules**:

- Query aliases and form field names remain exactly as today.
- Empty values are omitted from retry URLs and hidden fields as current
  templates do.
- Metadata truncation keeps current maximum lengths: gateway/AP MAC 17,
  VLAN ID 8, SSID 64, radio ID 2.

### 2. GuestAuthorizationDependencies

**Purpose**: Group resolved dependencies currently passed to
`_process_authorization`.

| Attribute | Existing source |
|-----------|-----------------|
| `rate_limiter` | `RateLimiter` FastAPI dependency or override |
| `unified_code_service` | `UnifiedCodeService` dependency or override |
| `redirect_validator` | `RedirectValidator` dependency or override |
| `session` | SQLModel `Session` |
| `audit_service` | `get_audit_service` |
| `portal_config` | `get_portal_config_dep` |
| `omada_adapter` | `get_omada_adapter` |

**Business rules**:

- GET submissions continue to use `_get_optional_session` and dependency
  overrides exactly as today.
- POST submissions continue to use FastAPI dependency injection.
- No dependency is made global or shared across requests unless it already is.

### 3. GuestAuthorizationContext

**Purpose**: Carry per-request values computed during authorization.

| Attribute | Description |
|-----------|-------------|
| `client_ip` | Trusted-proxy-aware IP from `get_client_ip` |
| `mac_address` | Validated normalized MAC address |
| `validation_result` | Existing `UnifiedCodeService.validate_code` result |
| `vlan_meta` | Current VLAN audit metadata keys and values |
| `grant` | Current `AccessGrant` under construction or persisted |
| `retry_query` | URL-encoded retry parameters stored on request state |

**Business rules**:

- CSRF validation occurs before rate limiting and MAC extraction as today.
- Rate-limit failures log current metadata and raise 429 with `Retry-After`.
- Successful authorization clears the rate limit for the resolved client IP.

### 4. AuthorizationDecisionResult

**Purpose**: Return the result of voucher or booking decision helpers.

| Attribute | Voucher path | Booking path |
|-----------|--------------|--------------|
| `grant` | Result from `VoucherService.redeem` | Newly created pending `AccessGrant` |
| `target_type` | `voucher` | `booking` |
| `target_id` | Normalized voucher code for denials; grant ID on success | Normalized code for denials; grant ID on success |
| `vlan_meta` | Existing voucher VLAN metadata | Existing booking VLAN metadata |

**Business rules**:

- Exceptions and HTTP status mappings remain unchanged.
- Audit actor, action, outcome, target, and metadata keys remain unchanged.
- Booking references are stored with original case from the matched event.

## Relationships

```text
FastAPI route parameters
        │
        ├──> GuestOmadaParams ───────┐
        │                            │
        ├──> GuestAuthorizationDependencies
        │                            │
        └──> GuestAuthorizationContext
                                     │
             UnifiedCodeService.validate_code
                     │
          ┌──────────┴──────────┐
          │                     │
   voucher helper         booking helper
          │                     │
          └──────> AuthorizationDecisionResult
                         │
                  controller helper
                         │
                  AccessGrant persisted
                         │
                  redirect/error helpers
```

## Data Migration

No migration is required. Existing rows remain valid and future implementation
must not alter schema creation, inline migrations, configuration fields, or
stored data formats.
