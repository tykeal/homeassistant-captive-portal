SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Omada OpenAPI Migration

**Feature Branch**: `013-omada-openapi-migration`
**Created**: 2026-06-26
**Status**: Draft
**Input**: Migrate Omada guest authorization to the documented OpenAPI while preserving transparent legacy API fallback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - OpenAPI Guest Access (Priority: P1)

An operator runs the captive portal against an Omada controller that supports
Omada OpenAPI and has OpenAPI app credentials configured. Guests continue to
redeem vouchers or booking codes exactly as before, but their device is
authorized and later deauthorized through the documented OpenAPI controller
surface instead of the legacy hotspot operator API.

**Why this priority**: Moving the primary authorization path to the supported
OpenAPI is the core value of the feature and reduces reliance on the legacy
external portal API without changing the guest experience.

**Independent Test**: Can be fully tested by configuring an OpenAPI-capable
controller with valid OpenAPI credentials, redeeming a valid guest code, and
verifying that authorize, revoke, expiry, and status behavior match the
existing externally observable behavior while the selected backend is OpenAPI.

**Acceptance Scenarios**:

1. **Given** an OpenAPI-capable controller, valid OpenAPI credentials, and
   `openapi_mode` set to `auto`, **When** the add-on starts and the OpenAPI
   capability probe succeeds, **Then** guest authorization, revocation, and
   status operations use the OpenAPI backend.
2. **Given** the OpenAPI backend is selected and a guest submits a valid
   voucher or booking code, **When** the system authorizes the guest device,
   **Then** the guest receives the same success outcome, redirect behavior,
   grant state, and network access capability provided by the existing Omada
   integration.
3. **Given** an active OpenAPI-backed grant reaches its add-on-managed expiry
   time, **When** the grant-expiry timer runs, **Then** the system
   deauthorizes the guest device through the selected controller backend and
   marks the grant expired according to existing grant behavior.
4. **Given** an admin revokes an active OpenAPI-backed grant before its expiry,
   **When** the revoke action is accepted, **Then** the system deauthorizes the
   guest device through the selected controller backend and presents the same
   admin-visible revocation result as today.

---

### User Story 2 - Legacy Fallback Continuity (Priority: P2)

An operator has an older Omada controller, does not configure OpenAPI
credentials, or experiences an OpenAPI capability probe failure in automatic
mode. The add-on continues to use the legacy hotspot/external portal API so
existing deployments keep working without configuration changes.

**Why this priority**: Backward compatibility is required so the migration does
not break currently deployed controllers or force operators to create new
credentials before upgrading.

**Independent Test**: Can be fully tested by upgrading an existing deployment
with only legacy credentials configured and verifying that guest authorize,
revoke, status, and expiry behavior remains unchanged.

**Acceptance Scenarios**:

1. **Given** an existing deployment with controller URL, legacy username,
   legacy password, site name, controller ID, and SSL settings configured but
   no OpenAPI client credentials, **When** the upgraded add-on starts, **Then**
   the system selects the legacy backend automatically and requires no operator
   action.
2. **Given** `openapi_mode` is `auto` and OpenAPI credentials are present,
   **When** the OpenAPI capability probe fails because the controller is too
   old, the OpenAPI endpoint is unavailable, credentials are rejected, or the
   controller cannot be reached during the probe, **Then** the system selects
   the legacy backend and records an operator-actionable warning.
3. **Given** the legacy backend is selected by automatic fallback, **When** a
   guest is authorized, an admin revokes a grant, a grant expires, or status is
   requested, **Then** the outcome is equivalent to the pre-migration legacy
   behavior.
4. **Given** an existing deployment upgrades without changing configuration,
   **When** guests redeem valid access codes after the upgrade, **Then** the
   deployment continues to authorize guests without requiring OpenAPI
   credential configuration.

---

### User Story 3 - Backend Selection Control (Priority: P3)

An operator can choose automatic selection, force the OpenAPI backend for
validation or rollout, or force the legacy backend for compatibility or
rollback by setting `openapi_mode` to `auto`, `openapi`, or `legacy`.

**Why this priority**: Explicit control helps operators test, troubleshoot, and
roll back the migration safely while automatic selection remains the default
for normal use.

**Independent Test**: Can be fully tested by changing only `openapi_mode` and
credential presence, restarting the add-on, and verifying the selected backend
and failure behavior for each supported mode.

**Acceptance Scenarios**:

1. **Given** `openapi_mode` is unset or set to `auto`, **When** the add-on
   starts, **Then** the system selects OpenAPI only when OpenAPI credentials
   are present and the OpenAPI capability probe succeeds; otherwise it selects
   legacy.
2. **Given** `openapi_mode` is `legacy`, **When** the add-on starts, **Then**
   the system selects the legacy backend regardless of configured OpenAPI
   credentials and does not require an OpenAPI capability probe to succeed.
3. **Given** `openapi_mode` is `openapi`, **When** required OpenAPI
   credentials are missing or the OpenAPI capability probe fails, **Then** the
   system does not silently fall back to legacy and instead reports a clear
   configuration or capability error.
4. **Given** `openapi_mode` has any value other than `auto`, `openapi`, or
   `legacy`, **When** configuration is validated, **Then** the system rejects
   the configuration with an actionable message that lists the supported
   values.

---

### Edge Cases

- What happens when OpenAPI credentials are only partially configured? Automatic
  mode treats the OpenAPI configuration as incomplete, selects legacy when
  legacy credentials are available, and reports the missing OpenAPI credential
  without exposing secret values.
- What happens when `openapi_mode` is `openapi` and legacy credentials are the
  only credentials configured? The add-on reports that OpenAPI mode cannot be
  used until both `client_id` and `client_secret` are configured.
- What happens when `openapi_mode` is `auto`, OpenAPI credentials are present,
  and legacy credentials are absent? A successful OpenAPI probe selects
  OpenAPI; a failed probe reports that no usable backend is available rather
  than selecting an unconfigured legacy backend.
- What happens when the OpenAPI backend is selected but a later token refresh,
  site lookup, authorization, revocation, or status request fails? The
  operation fails gracefully with existing user/admin error semantics, logs an
  actionable controller error, and does not switch backends mid-operation.
- What happens when a grant expires while the controller is temporarily
  unreachable? The add-on records the controller deauthorization failure using
  existing audit/error behavior and keeps grant state consistent with current
  expiry handling.
- What happens when a MAC address is unavailable or invalid? The system rejects
  the operation before calling either controller backend, preserving existing
  MAC validation behavior.
- What happens when controller SSL verification is disabled for a self-signed
  certificate? The selected backend honors the existing SSL verification
  setting consistently.
- What happens when secrets are logged during startup, probing, or errors?
  OpenAPI client secrets and legacy passwords are never emitted in logs,
  diagnostics, validation messages, or audit records.

## Requirements *(mandatory)*

### Functional Requirements

#### Backend Capability and Selection

- **FR-001**: The system MUST support two Omada controller backends: the
  documented OpenAPI backend and the existing legacy hotspot/external portal
  backend.
- **FR-002**: The system MUST preserve the existing externally observable
  Omada capabilities across both backends: guest authorization by MAC, guest
  deauthorization/revocation by MAC, grant-expiry deauthorization, and
  best-effort guest status.
- **FR-003**: The system MUST select a controller backend at add-on startup
  based on configured credentials, `openapi_mode`, and an OpenAPI capability
  probe.
- **FR-004**: In `auto` mode, the system MUST select the OpenAPI backend only
  when both OpenAPI credentials are configured and the OpenAPI capability probe
  succeeds.
- **FR-005**: In `auto` mode, the system MUST select the legacy backend when
  OpenAPI credentials are absent or the OpenAPI capability probe fails, provided
  legacy credentials are configured.
- **FR-006**: In `legacy` mode, the system MUST select the legacy backend and
  MUST NOT require OpenAPI credentials or a successful OpenAPI capability probe.
- **FR-007**: In `openapi` mode, the system MUST require OpenAPI credentials
  and a successful OpenAPI capability probe; it MUST NOT silently fall back to
  the legacy backend when either condition fails.
- **FR-008**: The system MUST report a clear startup or configuration error
  when the configured mode and credentials leave no usable Omada backend.
- **FR-009**: The OpenAPI capability probe MUST verify that configured OpenAPI
  credentials can obtain a successful OpenAPI token for the target controller.
- **FR-010**: A failed OpenAPI capability probe in automatic mode MUST produce
  an operator-actionable warning that identifies fallback to legacy without
  exposing credentials or tokens.
- **FR-011**: Once a backend is selected at startup, the system MUST use that
  backend consistently for controller operations until the add-on restarts or
  is reconfigured.
- **FR-012**: When the OpenAPI backend is selected and a mid-session token
  acquisition or renewal attempt fails, the system MUST fail the pending or
  next controller operation with the same user/admin-facing error semantics
  used for controller errors, MUST log an actionable error without exposing
  credential or token material, and MUST NOT switch to the legacy backend
  for the remainder of the current add-on run.
- **FR-013**: When OpenAPI credentials are only partially configured in
  automatic mode and legacy credentials are available, the system MUST select
  legacy and emit an operator-actionable warning identifying the missing
  OpenAPI credential field without exposing secret values.

#### Configuration and Migration

- **FR-014**: The Omada configuration MUST add optional `client_id` and
  `client_secret` fields for OpenAPI application credentials.
- **FR-015**: The Omada configuration MUST add `openapi_mode` with supported
  values `auto`, `openapi`, and `legacy`; the default MUST be `auto`.
- **FR-016**: The system MUST reject any `openapi_mode` value other than
  `auto`, `openapi`, or `legacy` with an actionable validation message.
- **FR-017**: Existing `username` and `password` configuration fields MUST
  remain available for the legacy backend.
- **FR-018**: Existing deployments that do not configure OpenAPI credentials
  MUST require no operator action after upgrade and MUST continue using the
  legacy backend automatically.
- **FR-019**: `client_secret` MUST be protected at rest and in runtime output
  with the same secrecy guarantees as the existing Omada password.
- **FR-020**: The system MUST never log OpenAPI client secrets, OpenAPI access
  tokens, OpenAPI refresh tokens, or legacy passwords.
- **FR-021**: The existing controller URL, site name, controller ID, and SSL
  verification settings MUST apply consistently to whichever backend is
  selected.

#### Guest Authorization, Revocation, and Status

- **FR-022**: When the OpenAPI backend is selected, guest authorization MUST
  authorize the guest device by MAC through the documented Omada OpenAPI
  hotspot client authorization capability.
- **FR-023**: When the OpenAPI backend is selected, admin revocation,
  early revocation, and grant-expiry deauthorization MUST deauthorize the guest
  device by MAC through the documented Omada OpenAPI hotspot client
  deauthorization capability.
- **FR-024**: When the OpenAPI backend is selected, best-effort guest
  status MUST query guest authorization state through the documented Omada
  OpenAPI hotspot client status capability.
- **FR-025**: When the legacy backend is selected, guest authorization,
  revocation, grant expiry, and status MUST retain the current legacy API
  behavior.
- **FR-026**: The system MUST preserve existing guest-facing outcomes for valid
  code redemption, invalid code handling, successful authorization, controller
  authorization failure, and post-authorization redirect behavior.
- **FR-027**: The system MUST preserve existing admin-facing outcomes for
  successful revocation, already-revoked grants, controller revocation failure,
  and grants that have no controller authorization to revoke.
- **FR-028**: The system MUST preserve existing best-effort status semantics so
  callers receive equivalent status meaning regardless of selected backend,
  even if controller response details differ.
- **FR-029**: The system MUST validate MAC availability and format before
  attempting authorization, revocation, or status calls through either backend.

#### Duration and Expiry Policy

- **FR-030**: Per-grant access duration MUST NOT depend on any per-call
  controller duration parameter in the OpenAPI authorization request.
- **FR-031**: Operators MUST be able to rely on a controller hotspot portal
  profile configured with a sufficiently generous maximum duration while the
  add-on enforces actual grant duration itself.
- **FR-032**: The add-on MUST use its existing grant-expiry timer as the source
  of truth for ending network access and MUST call the selected backend's
  deauthorization/revoke capability when a grant expires.
- **FR-033**: Early/admin revocation MUST use the selected backend's
  deauthorization/revoke capability rather than waiting for controller-side
  duration expiry.
- **FR-034**: Operator-facing configuration guidance MUST state that the
  controller hotspot portal profile duration needs to exceed the longest
  expected add-on-managed grant duration.

#### Compatibility, Observability, and Safety

- **FR-035**: The system MUST support controllers that do not expose OpenAPI by
  using the legacy backend when automatic selection is configured and legacy
  credentials are available.
- **FR-036**: The system MUST emit logs that identify the selected backend and
  the reason for selection without exposing credential material.
- **FR-037**: Controller errors during authorization, revocation, expiry, or
  status operations MUST be reported through the same user/admin-facing error
  channels used by the existing Omada integration.
- **FR-038**: Audit logging MUST continue to record guest authorization and
  revocation actions with enough context to distinguish successful controller
  actions from controller failures.
- **FR-039**: The OpenAPI migration MUST NOT introduce new externally visible
  guest or admin workflows beyond the additional backend selection
  configuration.

### Key Entities

- **Omada Configuration**: Operator-provided controller settings. Key
  attributes include controller URL, site name, controller ID, SSL
  verification setting, legacy username and password, OpenAPI client ID and
  client secret, and backend selection mode.
- **Controller Backend Selection**: The startup decision that identifies whether
  controller operations for the current add-on run use OpenAPI or legacy.
  Attributes include requested mode, credential availability, probe result,
  selected backend, and fallback or error reason.
- **Guest Access Grant**: The add-on's record of a guest device's network
  access. Key attributes include MAC address, grant status, start time, expiry
  time, and controller authorization state. The grant expiry time remains the
  source of truth for access duration.
- **Controller Capability Probe Result**: The outcome of checking whether the
  target controller can use configured OpenAPI credentials. Key attributes
  include success or failure, failure category, and whether automatic fallback
  is allowed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In automatic mode with valid OpenAPI credentials and an
  OpenAPI-capable controller, 100% of guest authorize, revoke, expiry, and
  status contract tests select and exercise the OpenAPI backend.
- **SC-002**: In automatic mode without OpenAPI credentials, 100% of existing
  legacy-only configuration tests continue to select the legacy backend with no
  required configuration changes.
- **SC-003**: In automatic mode with configured OpenAPI credentials but an
  unsupported controller, 100% of fallback tests select legacy when legacy
  credentials are available and emit an operator-actionable warning.
- **SC-004**: In forced OpenAPI mode, 100% of missing-credential or failed-probe
  tests fail clearly without using the legacy backend.
- **SC-005**: In forced legacy mode, 100% of backend-selection tests choose
  legacy even when valid OpenAPI credentials are also present.
- **SC-006**: Successful guest authorization completes within 25 seconds of the
  add-on submitting the authorization request to the controller for both
  selected backends under normal controller conditions.
- **SC-007**: Expired or admin-revoked grants initiate selected-backend
  deauthorization within 5 seconds of the add-on processing the expiry or
  revoke event.
- **SC-008**: Automated secret-safety checks and review confirm that OpenAPI
  secrets, OpenAPI tokens, and legacy passwords appear in zero log, audit, or
  validation outputs.
- **SC-009**: Existing guest and admin workflows require zero additional steps
  after upgrade for deployments that continue using the legacy backend.

## Assumptions

- Omada OpenAPI support begins with Omada SDN Controller v5.13 or later; this
  version threshold is an assumption to verify during implementation and field
  testing.
- Controllers below the OpenAPI-capable version, controllers without OpenAPI
  enabled, and controllers lacking valid OpenAPI app credentials can continue
  to support the existing legacy hotspot/external portal API.
- The controller's hotspot portal profile can be configured with a maximum
  duration long enough that add-on-managed expiry occurs before the
  controller-side profile limit for normal guest grants.
- The existing add-on grant-expiry timer is reliable enough to be the source of
  truth for ending access duration across both backends.
- Existing guest authorization, admin revocation, status, audit logging, and
  error handling semantics are the baseline behavior to preserve unless this
  specification explicitly states otherwise.
- Operators who force `openapi` mode prefer a clear startup/configuration
  failure over an automatic downgrade to legacy behavior.
- Extra OpenAPI capabilities such as extending periods, forcing disconnects,
  deleting authorization records, or exposing hotspot statistics are outside
  the scope of this migration unless needed to preserve existing behavior.
