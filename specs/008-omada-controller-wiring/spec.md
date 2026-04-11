SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Omada Controller Integration Wiring

**Feature Branch**: `008-omada-controller-wiring`
**Created**: 2025-07-11
**Status**: Draft
**Input**: Wire the existing, fully-implemented OmadaClient and OmadaAdapter into the captive portal application lifecycle — covering addon config schema, application settings, service initialization scripts, application startup/shutdown, guest authorization flow, admin grant revocation, and contract tests.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Guest WiFi Authorization via Omada Controller (Priority: P1)

A guest arrives at a venue, connects to the WiFi, and is redirected to the captive portal. They enter a valid voucher code or booking code. The captive portal validates the code, creates an access grant, and then instructs the Omada controller to authorize the guest's device on the network. The guest's device gains internet access within seconds of submitting the form.

**Why this priority**: This is the core value proposition — without controller authorization, the captive portal creates grant records but guests never actually get network access. Nothing else matters if this doesn't work.

**Independent Test**: Can be fully tested by submitting a valid code on the guest portal and verifying that (a) the grant record transitions to ACTIVE status, (b) the controller receives the authorize call with the correct MAC address and expiry, and (c) the controller's grant identifier is stored on the grant record.

**Acceptance Scenarios**:

1. **Given** a guest is on the captive portal and the Omada controller is configured, **When** they submit a valid voucher code, **Then** the system creates a PENDING grant, sends an authorize request to the Omada controller with the guest's MAC address and the voucher's expiry time, transitions the grant to ACTIVE on success, and stores the controller-assigned grant identifier on the grant record.
2. **Given** a guest submits a valid booking code, **When** the Omada controller accepts the authorization, **Then** the grant transitions to ACTIVE and the guest is redirected to the success page (or continue URL) with internet access enabled.
3. **Given** a guest submits a valid code, **When** the Omada controller rejects the authorization request (e.g., network error, controller offline, authentication failure), **Then** the grant is marked as FAILED, the guest sees a user-friendly error message explaining that network access could not be enabled, and the failure is recorded in the audit log.
4. **Given** the Omada controller is NOT configured (no controller URL set), **When** a guest submits a valid code, **Then** the system creates the grant and transitions it to ACTIVE without making any controller calls (graceful degradation for development/testing environments).

---

### User Story 2 — Admin Revokes Guest Network Access (Priority: P2)

An admin reviews the active grants list and decides to revoke a guest's access — perhaps the guest has violated terms of use or the access was granted in error. The admin clicks "Revoke" in the admin UI. The system revokes the grant in the database AND instructs the Omada controller to deauthorize the guest's MAC address, immediately cutting off their network access.

**Why this priority**: Revocation is essential for security and operational control. Without it, admins can mark grants as revoked in the database but guests retain actual network access on the controller until their grant naturally expires.

**Independent Test**: Can be fully tested by creating an active grant, revoking it through the admin interface, and verifying that (a) the grant status changes to REVOKED in the database, (b) the Omada controller receives the revoke call with the correct MAC address, and (c) the guest's device loses network access.

**Acceptance Scenarios**:

1. **Given** an active grant exists with a stored MAC address and the Omada controller is configured, **When** an admin revokes the grant via the admin UI or API, **Then** the system updates the grant status to REVOKED in the database AND sends a revoke request to the Omada controller with the guest's MAC address.
2. **Given** an admin revokes a grant, **When** the Omada controller confirms the revocation (or returns "already revoked"), **Then** the revocation is treated as successful and the admin sees confirmation.
3. **Given** an admin revokes a grant, **When** the Omada controller is unreachable or returns an error, **Then** the database grant is still marked REVOKED, the controller error is logged, and the admin is informed that the database was updated but the controller revocation may need manual attention.
4. **Given** the Omada controller is NOT configured, **When** an admin revokes a grant, **Then** only the database grant status is updated (existing behavior preserved).

---

### User Story 3 — Addon Configuration for Omada Controller (Priority: P3)

A Home Assistant administrator installs the captive portal addon and wants to connect it to their Omada SDN controller. They navigate to the addon's configuration panel in Home Assistant, enter the controller URL, credentials, site name, and controller ID. When the addon restarts, it picks up these settings and uses them to communicate with the Omada controller.

**Why this priority**: Configuration is a prerequisite for the other stories but is lower priority because the system must work without it (graceful degradation). The plumbing from addon config → environment variables → application settings is foundational infrastructure.

**Independent Test**: Can be fully tested by setting Omada configuration options in the addon config, restarting the addon, and verifying that the application starts with the correct Omada settings loaded and an active controller connection.

**Acceptance Scenarios**:

1. **Given** the addon config includes Omada controller settings (URL, username, password, site, controller ID), **When** the addon starts, **Then** the s6 run scripts read these values and pass them to the application as environment variables, and the application loads them into its settings model.
2. **Given** the addon config includes Omada settings, **When** the admin and guest applications start up, **Then** each application instantiates a controller client and adapter during its startup phase and stores them for use during request handling.
3. **Given** the addon config does NOT include an Omada URL, **When** the addon starts, **Then** the application starts normally without initializing any controller client, with no errors and no warnings; it may emit an informational log message.
4. **Given** the Omada password is configured, **When** the application logs its configuration at startup, **Then** the password value is never written to any log output.
5. **Given** the application is running with a controller connection, **When** the application shuts down, **Then** the controller client connection is cleanly closed and all resources are released.

---

### User Story 4 — Contract Tests Validate Integration Wiring (Priority: P4)

A developer working on the captive portal runs the contract test suite. The existing contract tests (previously skipped) now execute and validate that the Omada integration wiring works correctly — that authorize requests produce the right payloads, revoke requests target the right endpoints, and error/retry scenarios are handled properly.

**Why this priority**: Tests validate the correctness of the wiring but are not user-facing. They prevent regressions and document expected behavior for future maintainers.

**Independent Test**: Can be fully tested by running the contract test suite and verifying that all previously-skipped tests now pass (or fail for legitimate reasons that are addressed).

**Acceptance Scenarios**:

1. **Given** the contract tests in the test suite, **When** a developer runs the test suite, **Then** all previously-skipped Omada contract tests execute without skip markers.
2. **Given** the contract tests, **When** they run, **Then** each test validates a specific aspect of the integration wiring (authorization payload structure, revocation request format, error handling, retry behavior) using the actual adapter and client code.
3. **Given** the contract tests, **When** they run in a CI environment without a real Omada controller, **Then** they use appropriate test doubles or mocks and do not require network access to an actual controller.

---

### Edge Cases

- What happens when the Omada controller is configured but unreachable? The application should start normally (no startup health check). When a guest authorization or admin revocation is attempted, the operation should fail gracefully with a user-facing error message and an audit log entry.
- What happens when the controller session expires mid-operation? The existing client's retry logic with re-authentication should handle this transparently.
- What happens when a guest's MAC address cannot be extracted from request headers? The authorization flow should reject the request before attempting any controller call (existing behavior).
- What happens when the admin revokes a grant that was created before the Omada integration was wired up (i.e., the grant has no controller grant ID or MAC)? The revocation should update the database only and skip the controller call.
- What happens when two simultaneous authorization requests arrive for the same MAC address? The controller should handle idempotent authorization; the application should not need special deduplication logic.
- What happens when the SSL certificate of the Omada controller is self-signed? The `verify_ssl` configuration option should allow disabling certificate verification for self-signed deployments.

## Requirements *(mandatory)*

### Functional Requirements

#### Configuration & Settings

- **FR-001**: The addon configuration schema MUST include optional fields for Omada controller connection: controller URL, username, password, site name, controller ID, and SSL verification toggle.
- **FR-002**: The application settings model MUST include corresponding fields for all Omada configuration options with sensible defaults (empty/unset for connection details, enabled for SSL verification).
- **FR-003**: The s6 service run scripts MUST read Omada configuration values from the addon options and export them as prefixed environment variables for the application to consume.
- **FR-004**: The application MUST support configuring the Omada connection through both addon options (highest priority) and environment variables (for development/testing).
- **FR-005**: The application MUST never log the Omada password value in any log level or output.

#### Application Lifecycle

- **FR-006**: Both the admin application (port 8080) and guest application (port 8099) MUST initialize a controller client and adapter during startup when Omada configuration is present.
- **FR-007**: Both applications MUST cleanly close the controller client connection during shutdown.
- **FR-008**: When Omada configuration is absent (no controller URL), both applications MUST start normally without initializing any controller components and without producing errors.
- **FR-009**: When Omada configuration is present, the application MUST still start without performing a controller login or reachability check at startup; if the controller is unreachable, the resulting warning/error MUST be handled when the first authorize or revoke operation is attempted rather than during startup.

#### Guest Authorization Flow

- **FR-010**: After creating a PENDING access grant, the guest authorization flow MUST call the controller adapter's authorize method with the guest's MAC address and the grant's expiry time.
- **FR-011**: On successful controller authorization, the system MUST transition the grant status from PENDING to ACTIVE and store the controller-returned grant identifier on the grant record.
- **FR-012**: On failed controller authorization, the system MUST mark the grant as FAILED, display a user-friendly error message to the guest, and record the failure in the audit log.
- **FR-013**: When no controller is configured, the authorization flow MUST skip the controller call and transition the grant directly to ACTIVE (preserving current development/testing behavior).

#### Grant Revocation

- **FR-014**: When an admin revokes a grant, the system MUST call the controller adapter's revoke method with the grant's MAC address to deauthorize the device on the network.
- **FR-015**: Revocation on the controller MUST be treated as successful when the controller confirms deauthorization OR reports the device was already deauthorized (idempotent behavior).
- **FR-016**: When the controller is unreachable during revocation, the database grant MUST still be marked as REVOKED, the error MUST be logged, and the admin MUST be informed of the partial failure.
- **FR-017**: When no controller is configured, revocation MUST update only the database (preserving current behavior).
- **FR-018**: When revoking a grant that has no associated MAC address (legacy grants created before this integration), the system MUST skip the controller call and update only the database.

#### Documentation

- **FR-019**: The setup documentation (`docs/tp_omada_setup.md`) MUST reference port 8099 (guest portal) instead of port 8080 (admin/ingress) in all external portal URL examples, firewall rule examples, and troubleshooting commands. Port 8080 is the HA ingress port behind authentication; guests connect via port 8099.

#### Contract Tests

- **FR-020**: All existing contract tests in the Omada test directory MUST be unskipped and made functional.
- **FR-021**: Contract tests MUST validate the integration wiring without requiring a live Omada controller.
- **FR-022**: Contract tests MUST cover authorization flow, revocation flow, and error/retry handling.

### Key Entities

- **AccessGrant**: Represents a guest's authorized access period. Key attributes relevant to this feature: MAC address (identifies the device), status (PENDING → ACTIVE or FAILED; ACTIVE → REVOKED), controller grant ID (identifier returned by the Omada controller after successful authorization), start and end times.
- **Omada Controller Connection**: Represents the configured connection to a TP-Link Omada SDN controller. Key attributes: URL, credentials, site, controller ID, SSL verification setting. Lifecycle is tied to application startup/shutdown.
- **Addon Configuration**: The set of user-configurable options exposed in the Home Assistant addon configuration panel. Each Omada option maps to an environment variable which maps to an application setting field.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a guest submits a valid code on the captive portal with an Omada controller configured, their device gains network access within 10 seconds of form submission.
- **SC-002**: When an admin revokes an active grant, the guest's device loses network access within 10 seconds of the revocation action.
- **SC-003**: 100% of previously-skipped Omada contract tests execute and pass in the test suite.
- **SC-004**: The application starts and operates normally when no Omada controller is configured, with zero errors or warnings related to the missing controller.
- **SC-005**: All 8 integration gaps (config schema, settings model, s6 scripts, app lifespan, authorization flow, revocation flow, documentation port references, contract tests) are closed and functionally connected.
- **SC-006**: Controller authorization failures result in a user-facing error message within 30 seconds (accounting for retry backoff), never leaving the guest in an ambiguous state.
- **SC-007**: The Omada password never appears in any application log output regardless of log level.

## Assumptions

- The existing OmadaClient and OmadaAdapter implementations are correct, tested, and ready for production use — this feature is exclusively about wiring, not about modifying controller client logic.
- The Omada controller's hotspot external portal API endpoint paths (`/extportal/auth`, `/extportal/revoke`, `/extportal/session`) are stable and match the existing client implementation.
- Guest MAC addresses are available in HTTP request headers (set by the captive portal network infrastructure) — the existing MAC extraction logic in the guest portal route is sufficient.
- The AccessGrant model already has (or can be extended to include) a field for storing the controller-assigned grant identifier (`controller_grant_id`).
- The existing three-tier configuration precedence (addon options → environment variables → defaults) in AppSettings is the correct pattern to follow for the new Omada fields.
- The s6 run scripts use `bashio::config` for reading addon options — this existing pattern will be extended for Omada options.
- Contract tests can use mocks/test doubles for the Omada controller since the tests validate wiring correctness, not controller API compatibility.
- Both the admin app (port 8080) and guest app (port 8099) can independently instantiate their own OmadaClient/OmadaAdapter instances — sharing a single instance across processes is not required.
- The Omada controller connection is not validated at startup (no "ping" or health check) — connection issues are handled when authorization or revocation calls are made.
- Bandwidth limit parameters (upload/download kbps) for authorization are either derived from the voucher/booking configuration or use defaults of 0 (unlimited) — this feature does not define new UI for setting bandwidth limits.
