SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0

# Data Model: Guest Auth Complexity Cleanup

**Feature**: 015-guest-auth-complexity-cleanup
**Date**: 2026-06-29

## Schema Decision

No persistent schema changes are planned or allowed. Existing SQLModel tables,
columns, defaults, inline migrations, repository behavior, controller payloads,
route parameters, form fields, aliases, and configuration fields remain
unchanged. The only planned data-model additions are frozen in-memory
parameter objects for internal helper calls.

## Existing Persistent Entities

### 1. AccessGrant (Unchanged)

**Location**: `addon/src/captive_portal/models/access_grant.py`

| Field/behavior | Preservation requirement |
|----------------|--------------------------|
| `mac` / `device_id` | Continue storing the validated normalized MAC address. |
| `booking_ref` | Preserve the case-sensitive booking identifier from the matched event. |
| `user_input_code` | Preserve the guest's original submitted booking input. |
| `integration_id` | Preserve the matched rental-control integration ID. |
| `start_utc` / `end_utc` | Preserve voucher duration and booking window/grace rounding. |
| `status` | Preserve PENDING, ACTIVE, FAILED, and controller transitions. |
| `controller_grant_id` | Preserve adapter result storage on controller success. |
| Omada metadata fields | Preserve current truncation for gateway/AP MAC, VLAN, SSID, and radio ID. |

### 2. Voucher (Unchanged)

Voucher validation, redemption, expiry, revocation, device-limit behavior,
duplicate-device behavior, status updates, and VLAN allowlist checks remain
owned by existing models, repositories, and services.

### 3. HAIntegrationConfig and RentalControlEvent (Unchanged)

Booking lookup across integrations, identifier attribute use, checkout grace,
window checks, duplicate grant checks, VLAN allowlist checks, and
missing-integration behavior remain unchanged.

### 4. PortalConfig (Unchanged)

Trusted proxy networks, redirect validation configuration, and guest security
behavior remain unchanged. `portal_settings_ui.py:110` remains out of scope for
this feature and is tracked separately by issue #190.

## Internal In-Memory Objects

These objects are not database models and must not be serialized as new API
contracts. They exist only to make helper boundaries smaller and typed.

### 1. GuestOmadaParams (Existing, unchanged or frozen)

**Location**: `guest_authorization/context.py`

**Purpose**: Keep grouping Omada metadata and success-redirect input captured by
routes before helper orchestration.

| Attribute | Source field | Existing destination |
|-----------|--------------|----------------------|
| `client_mac` | `clientMac` query or `client_mac` form | MAC extraction and retry URL |
| `client_ip` | `clientIp` query | GET form hidden field/debug context |
| `site` | `site` query/form | Retry URL and legacy site override |
| `gateway_mac` | `gatewayMac` query or `gateway_mac` form | Grant and controller metadata |
| `ap_mac` | `apMac` query or `ap_mac` form | Grant and controller metadata |
| `radio_id` | `radioId` query or `radio_id` form | Grant and controller metadata |
| `ssid_name` | `ssidName` query or `ssid_name` form | Grant and controller metadata |
| `vid` | `vid` query/form | VLAN, grant, and controller metadata |
| `t` | `t` query | GET hidden field only |
| `redirect_url` | `redirectUrl` query | Form continue fallback |
| `continue_url` | `continue` query or `continue_url` form | Safe success redirect candidate |

**Rules**: Query aliases, form fields, hidden fields, retry query keys, and
metadata truncation remain exactly as today.

### 2. GuestAuthorizationDependencies (Existing, unchanged or frozen)

**Location**: `guest_authorization/context.py`

**Purpose**: Keep grouping resolved request dependencies for shared
authorization orchestration.

| Attribute | Existing source |
|-----------|-----------------|
| `rate_limiter` | FastAPI dependency or GET override resolution |
| `unified_code_service` | FastAPI dependency or GET override resolution |
| `redirect_validator` | FastAPI dependency or GET override resolution |
| `session` | SQLModel `Session` |
| `audit_service` | `get_audit_service` |
| `portal_config` | `get_portal_config_dep` |
| `omada_adapter` | `get_omada_adapter` |

**Rules**: Dependency lifetimes and override behavior remain unchanged.

### 3. GuestAuthorizationContext (Existing mutable request state)

**Location**: `guest_authorization/context.py`

**Purpose**: Preserve current request-state introspection for values discovered
during authorization.

| Attribute | Description |
|-----------|-------------|
| `client_ip` | Trusted-proxy-aware client IP. |
| `mac_address` | Validated normalized MAC address. |
| `validation_result` | Current `UnifiedCodeService.validate_code` result. |
| `vlan_meta` | Voucher or booking VLAN audit metadata. |
| `grant` | Current `AccessGrant` under construction or persistence. |
| `retry_query` | URL-encoded retry parameters stored on request state. |

**Rules**: This object may remain mutable because the flow fills it in stages;
new parameter-reduction objects should be frozen.

### 4. GuestDecisionContext (New frozen dataclass)

**Location**: `guest_authorization/context.py`

**Purpose**: Collapse repeated voucher and booking helper inputs without hiding
route behavior.

| Attribute | Description |
|-----------|-------------|
| `request` | Current FastAPI request for method, headers, app state, and audit context. |
| `audit_service` | Audit log writer for denial and error paths. |
| `client_ip` | Resolved trusted-proxy-aware IP. |
| `mac_address` | Validated normalized MAC address. |
| `vid` | Submitted VLAN ID, if any. |

**Rules**: Use `@dataclass(frozen=True, slots=True)`. Do not store submitted
`code` here; keep `validation_result` explicit at branch-helper call sites.

### 5. BookingGrantInput (New frozen dataclass)

**Location**: `guest_authorization/bookings.py`

**Purpose**: Collapse scalar grant-construction inputs for
`_create_booking_grant`.

| Attribute | Description |
|-----------|-------------|
| `mac_address` | Validated normalized MAC address. |
| `validation_result` | Validated booking code with original and normalized values. |
| `integration` | Matched `HAIntegrationConfig`. |
| `booking_identifier` | Case-preserved identifier from the matched event. |
| `start_utc` | Aware UTC booking start. |
| `effective_end` | Booking end plus checkout grace. |
| `now` | Single UTC timestamp shared across the booking decision. |

**Rules**: `_create_booking_grant(session, grant_input)` must preserve
`floor_to_minute(max(now, start_utc))`, `ceil_to_minute(effective_end)`, pending
status, integration ID, and original booking input storage.

### 6. BookingAuditContext (New frozen dataclass)

**Location**: `guest_authorization/bookings.py`

**Purpose**: Collapse repeated audit inputs for booking exception paths.

| Attribute | Description |
|-----------|-------------|
| `audit_service` | Audit log writer. |
| `request` | Current FastAPI request. |
| `client_ip` | Resolved client IP. |
| `mac_address` | Validated MAC address. |
| `validation_result` | Validated booking code. |

**Rules**: User-Agent lookup, actor, action, target ID, and metadata keys remain
unchanged.

### 7. BookingAuditFailure (New frozen dataclass)

**Location**: `guest_authorization/bookings.py`

**Purpose**: Collapse variable booking-error metadata for
`_audit_booking_error`.

| Attribute | Description |
|-----------|-------------|
| `error` | Stable audit metadata error value. |
| `outcome` | Existing audit outcome, `denied` or `error`. |
| `detail` | Diagnostic detail string preserved from the exception. |
| `target_type` | Optional target type; omitted for integration unavailable. |

**Rules**: Target ID remains the normalized booking code when `target_type` is
present.

## Relationships

```text
FastAPI route parameters
        │
        ├──> GuestOmadaParams
        ├──> GuestAuthorizationDependencies
        └──> orchestration.process_authorization
                    │
                    ├──> GuestAuthorizationContext on request.state
                    ├──> GuestDecisionContext
                    │       ├──> authorize_voucher(...)
                    │       └──> authorize_booking(...)
                    │               ├──> BookingGrantInput
                    │               ├──> BookingAuditContext
                    │               └──> BookingAuditFailure
                    └──> controller, audit, redirect helpers
```

## Data Migration

No migration is required. Existing rows remain valid and future implementation
must not alter schema creation, stored data formats, route contracts, controller
payload shapes, or operator configuration.
