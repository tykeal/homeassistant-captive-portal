SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: VLAN-Based Authorization Isolation

**Feature Branch**: `009-vlan-auth-isolation`
**Created**: 2025-07-14
**Status**: Draft
**Input**: User description: "Add VLAN ID mapping to the Home Assistant integration configuration so each Rental Control unit maps to specific guest VLAN(s). During guest WiFi authorization, validate that the connecting device's VLAN ID matches the booking's RC integration allowed VLANs. Reject authorization attempts where there is a VLAN mismatch."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - VLAN Validation During Booking Authorization (Priority: P1)

A property manager has 10 rental units, each assigned a dedicated guest VLAN (e.g., VLAN 50 for Unit A, VLAN 51 for Unit B). When a guest in Unit A connects to WiFi and enters their booking code, the system validates that the guest's device is on VLAN 50 — which matches Unit A's configured VLAN. If the guest is on a different VLAN (e.g., VLAN 51 for Unit B), the system rejects the authorization with a friendly error message, preventing cross-unit access.

**Why this priority**: This is the core security feature. Without VLAN validation, any guest on any VLAN can use any valid booking code, defeating the purpose of per-unit network isolation. This delivers immediate value by closing the primary security gap.

**Independent Test**: Can be fully tested by configuring one integration with allowed VLANs, then attempting authorization with matching and non-matching VLAN IDs. Delivers the fundamental isolation guarantee.

**Acceptance Scenarios**:

1. **Given** an integration config for Unit A with allowed VLAN 50 and a valid booking code for Unit A, **When** a guest on VLAN 50 submits that booking code, **Then** authorization proceeds normally and the guest receives WiFi access.
2. **Given** an integration config for Unit A with allowed VLAN 50 and a valid booking code for Unit A, **When** a guest on VLAN 51 submits that booking code, **Then** authorization is rejected with the message "This code is not valid for your network."
3. **Given** an integration config for Unit A with allowed VLANs 50 and 55 (multiple VLANs), **When** a guest on VLAN 55 submits a valid Unit A booking code, **Then** authorization proceeds normally.
4. **Given** a valid booking code and a guest device whose network/VLAN cannot be identified, **When** the guest submits the booking code, **Then** authorization is rejected with a user-friendly error indicating the network could not be identified.

---

### User Story 2 - Admin VLAN Configuration Per Integration (Priority: P2)

A property manager opens the admin integration settings page and configures allowed VLAN IDs for each Rental Control integration. They can add one or more VLAN IDs to each integration, edit existing assignments, and remove VLANs. The interface provides clear feedback about which VLANs are mapped to which units.

**Why this priority**: Admins need a way to configure VLAN mappings before the validation in Story 1 can function. However, configuration could initially be done via other means (direct data manipulation), making this important but secondary to the core validation logic.

**Independent Test**: Can be tested by navigating to the admin integrations page, adding VLAN IDs to an integration, saving, and verifying the VLANs are persisted and displayed correctly on reload.

**Acceptance Scenarios**:

1. **Given** an existing integration config with no VLANs configured, **When** an admin adds VLAN IDs "50, 51" and saves, **Then** the integration config is updated to include VLANs 50 and 51, and these are displayed on the integrations page.
2. **Given** an integration config with VLANs 50 and 51, **When** an admin removes VLAN 51 and saves, **Then** only VLAN 50 remains associated with the integration.
3. **Given** an admin entering an invalid VLAN value (e.g., negative number, non-numeric text, or a value above 4094), **When** they attempt to save, **Then** the system displays a validation error and does not save the invalid value.
4. **Given** two different integration configs, **When** an admin assigns VLAN 50 to both, **Then** the system accepts the configuration (the same VLAN may be shared across integrations if the admin chooses to do so).

---

### User Story 3 - VLAN Scoping for Voucher-Based Access (Priority: P3)

A property manager creates vouchers and optionally restricts them to specific VLANs. When a guest enters a voucher code, the system checks whether the voucher has VLAN restrictions. If restricted, the guest's VLAN must match one of the voucher's allowed VLANs. Unrestricted vouchers continue to work on any VLAN as they do today.

**Why this priority**: Vouchers are a secondary access mechanism. Most access is through booking codes tied to RC integrations. VLAN scoping for vouchers adds defense-in-depth but is not the primary isolation use case.

**Independent Test**: Can be tested by creating a VLAN-restricted voucher, then attempting redemption from matching and non-matching VLANs. Unrestricted vouchers should continue to work without any VLAN checks.

**Acceptance Scenarios**:

1. **Given** a voucher with no VLAN restrictions, **When** a guest on any VLAN submits the voucher code, **Then** authorization proceeds as normal (backward compatible).
2. **Given** a voucher restricted to VLANs 50 and 51, **When** a guest on VLAN 50 submits the voucher code, **Then** authorization proceeds normally.
3. **Given** a voucher restricted to VLAN 50 only, **When** a guest on VLAN 52 submits the voucher code, **Then** authorization is rejected with the message "This code is not valid for your network."
4. **Given** a voucher restricted to VLAN 50, **When** a guest whose device's network/VLAN cannot be identified, **Then** authorization is rejected with a user-friendly error.

---

### User Story 4 - Backward Compatibility for Unconfigured Integrations (Priority: P2)

A property manager who has not yet configured VLANs for any integrations upgrades to this version. The system continues to authorize guests exactly as before — no VLAN validation is performed when an integration has no allowed VLANs configured. This ensures a non-breaking upgrade path.

**Why this priority**: Preventing breakage on upgrade is critical for adoption. Existing deployments must continue to function without requiring immediate VLAN configuration.

**Independent Test**: Can be tested by upgrading without adding any VLAN configs and verifying all existing booking code flows work unchanged.

**Acceptance Scenarios**:

1. **Given** an integration config with no VLANs configured (empty list), **When** a guest submits a valid booking code from any VLAN, **Then** authorization proceeds as normal with no VLAN check.
2. **Given** a mix of integrations — some with VLANs configured and some without, **When** guests submit codes for the unconfigured integration, **Then** those authorizations proceed without VLAN checks while configured integrations enforce VLAN validation.

---

### Edge Cases

- What happens when the VLAN identifier provided during the redirect is not a valid integer (e.g., malformed, alphanumeric)? System should treat it as "no VLAN" and reject if the integration requires VLAN matching.
- What happens when an admin configures VLANs on an integration and then a guest with an active grant on a now-disallowed VLAN attempts to re-authorize? Existing active grants are not retroactively revoked; only new authorization attempts are validated.
- What happens when an integration has VLANs configured but all configured VLANs are later removed (set to empty)? The integration reverts to no-VLAN-check behavior (backward compatible).
- What happens if the same booking code matches events across multiple integrations with different VLAN allowlists? The VLAN allowlist acts as a discriminator: the system filters candidate integrations to those whose allowlist includes the device's VLAN. If exactly one integration matches, validation proceeds against it. If multiple integrations match (or none match after VLAN filtering), authorization is rejected with an ambiguity/mismatch error.
- What happens when a voucher with VLAN restrictions is partially redeemed (multi-use voucher) from VLAN 50, and a subsequent redemption attempt comes from VLAN 52 (not in allowlist)? The second redemption is rejected; each redemption attempt is independently validated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow administrators to configure a list of allowed VLAN IDs for each Home Assistant integration configuration.
- **FR-002**: System MUST validate VLAN IDs as integers in the range 1–4094 (per IEEE 802.1Q standard) when configured by an administrator.
- **FR-003**: System MUST, during booking code authorization, compare the connecting device's VLAN ID (from the controller redirect parameters) against the allowed VLANs of the integration that owns the matched booking event.
- **FR-004**: System MUST reject booking code authorization with a user-friendly error message ("This code is not valid for your network") when the device's VLAN does not match any of the integration's allowed VLANs.
- **FR-005**: System MUST skip VLAN validation entirely when an integration has no allowed VLANs configured (`None` or empty list), preserving backward compatibility.
- **FR-006**: System MUST reject authorization when the integration has VLANs configured but the device's VLAN ID is missing, empty, or not a valid integer.
- **FR-007**: System MUST allow administrators to optionally assign allowed VLAN IDs to individual vouchers.
- **FR-008**: System MUST validate voucher VLAN restrictions during voucher redemption, rejecting redemption when the device's VLAN does not match any of the voucher's allowed VLANs.
- **FR-009**: System MUST allow vouchers without VLAN restrictions to be redeemed from any VLAN (unrestricted by default).
- **FR-010**: System MUST record the VLAN validation result (allowed/rejected and the VLAN ID checked) in the audit log for each authorization attempt.
- **FR-011**: System MUST display configured VLAN IDs for each integration on the admin integrations management page.
- **FR-012**: System MUST allow the same VLAN ID to be assigned to multiple integrations (no cross-integration uniqueness constraint).
- **FR-013**: System MUST NOT retroactively revoke or modify existing active grants when VLAN configuration is changed on an integration or voucher.

### Key Entities

- **Integration VLAN Allowlist**: A set of permitted VLAN IDs associated with a Home Assistant integration configuration. Each entry is an integer (1–4094). An empty set means "no VLAN restriction" (all VLANs allowed). One integration may have multiple allowed VLANs (e.g., a unit with a primary and overflow network).
- **Voucher VLAN Allowlist**: An optional set of permitted VLAN IDs associated with a voucher. When empty or absent, the voucher is unrestricted. When populated, only devices on matching VLANs may redeem the voucher.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of authorization attempts from a non-matching VLAN are rejected when the integration has VLAN restrictions configured.
- **SC-002**: 100% of authorization attempts from a matching VLAN succeed (assuming the booking code and time window are valid).
- **SC-003**: Existing deployments with no VLAN configuration experience zero change in authorization behavior after upgrade.
- **SC-004**: Administrators can configure VLAN mappings for an integration in under 1 minute through the admin interface.
- **SC-005**: Every VLAN validation decision (accept or reject) is recorded in the audit log with the device's VLAN ID and the integration's allowed VLAN list.
- **SC-006**: Users who are rejected due to VLAN mismatch see a clear, non-technical error message that does not reveal VLAN IDs or internal network topology.

## Assumptions

- Each Rental Control integration corresponds to a single rental unit (or a small group of units sharing the same network segment). VLAN-to-integration mapping is a 1:N relationship (one integration can have multiple VLANs, but each VLAN's authorization is checked against a single integration's booking).
- The `vid` parameter provided by the Omada controller in the redirect URL is a reliable and trustworthy indicator of the device's VLAN assignment. VLAN spoofing at the network level is outside the scope of this feature (network-layer security is handled by the Omada controller and switch infrastructure).
- VLAN IDs in the deployment follow IEEE 802.1Q conventions (integer values 1–4094). Reserved VLANs (0 and 4095) are not used for guest networks.
- The existing admin authentication and role-based access control are sufficient to protect VLAN configuration — no additional authorization layer is needed for this feature.
- Voucher VLAN restrictions are configured at voucher creation time. Changing VLAN restrictions on existing vouchers is not required (admins can revoke and reissue if needed).
- The error message shown to guests on VLAN mismatch is intentionally vague ("This code is not valid for your network") to avoid leaking network topology information to end users.
