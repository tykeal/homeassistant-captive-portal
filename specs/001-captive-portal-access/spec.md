SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Captive Portal Guest Access

**Feature Branch**: `001-captive-portal-access`
**Created**: 2025-10-22
**Status**: Draft
**Input**: User description: "Create a captive portal for rental guest access to the network. It must be pluggable for multiple backend network controllers with TP-Omada as the initial implmentation target. It shall have an administration interface that allows for theming, viewing of current access grants, modification of access grants, creation of vouchers for additional flexibility to provide access grants. The captive portal will be designed to operate primarily as a Home Assistant addon but should be able to be run easily on a separate container host. The administration interface will be a webportal that is exposed. The administration system shall have the ability to have multiple administrative accounts defined. The first time the application is run it will ask for the initial administrator credentials to create and store. The system shall have an API to accept updates modifying access grants which will in turn correctly update the network controller with the changes to the grant. The system will be designed to use the Home Assistant REST API for getting information on Rental Control entities that are available and the administrator of the system will have the ability to define which entities should be used for getting information for guest access."

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Guest Obtains Network Access (Priority: P1)

A rental guest connects to the captive portal Wi-Fi SSID, is redirected to the portal page, enters required voucher or booking identifier, and receives temporary network access governed by defined duration and bandwidth constraints.

**Why this priority**: Core value delivery: enabling controlled guest access is the fundamental purpose of the portal.

**Independent Test**: Simulate guest connecting to SSID, present portal, submit valid voucher ID, confirm access granted and recorded without needing admin configuration workflows.

**Acceptance Scenarios**:

1. **Given** a guest with a valid active voucher, **When** they submit the voucher code, **Then** access is granted and expiration time stored.
2. **Given** a guest with an expired voucher, **When** they attempt submission, **Then** access is denied with clear message and no controller grant created.

---

### User Story 2 - Administrator Manages Access Grants (Priority: P2)

An administrator logs into the web admin portal, views current guest access grants (active, expired, upcoming), modifies a grant (extend duration), and revokes another grant.

**Why this priority**: Essential operational control enabling oversight and adjustments after initial guest access flow.

**Independent Test**: Create sample grants via API/fixtures, admin authenticates, performs extension and revocation, verify controller and internal state update independently of voucher creation workflows.

**Acceptance Scenarios**:

1. **Given** an active grant selected by admin, **When** they extend its duration, **Then** new expiration time is saved and controller updated.

---

### User Story 3 - Administrator Configures Home Assistant Entity Mapping (Priority: P3)

An administrator selects which Home Assistant Rental Control entities to associate with portal authorization logic (e.g., booking status, stay dates) and saves configuration so future voucher validations incorporate entity data.

**Why this priority**: Enables contextual automated access decisions beyond manual vouchers, increasing flexibility.

**Independent Test**: Provide mock HA REST API responses, admin chooses entities, saves mapping, retrieve mapping to confirm persistence without needing voucher redemption flow.

**Acceptance Scenarios**:

1. **Given** available rental entities discovered, **When** admin selects a subset and saves, **Then** configuration is persisted and retrievable.

---

### User Story 4 - Multi-Admin Account Provisioning (Priority: P4)

On first run the system prompts for initial admin credentials and stores them; later an existing admin creates additional admin accounts with role-based permissions (full vs read-only).

**Why this priority**: Security and operational scalability; not critical to initial guest access but required for broader management.

**Independent Test**: Fresh instance bootstrap creates first admin; subsequent admin login creates second admin; verify access differences if roles defined.

**Acceptance Scenarios**:

1. **Given** first-run state with no admins, **When** credentials entered, **Then** primary admin account is created.
2. **Given** an authenticated admin, **When** they create a new admin account, **Then** the account appears in admin list and can authenticate.

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- Voucher submitted twice concurrently (race condition) — must not create duplicate controller grants.
- Admin revokes a grant while a guest is actively connected — connection should drop within defined grace period (e.g., <30s) without lingering authorization.
- Home Assistant entity data temporarily unavailable — system should fall back to cached authorization assumptions for a short window and log degraded mode.
- First-run admin initialization interrupted mid-way — system must allow retry without partial credential leakage.
- Controller API latency or failure during grant update — must retry with exponential backoff and surface status in admin UI.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST present a captive portal page to unauthenticated guest devices connecting to designated SSID.
- **FR-002**: System MUST validate voucher codes and booking identifiers against internal store and HA Rental Control entities.
- **FR-003**: System MUST create, update, and revoke guest network access grants in the TP-Omada controller (initial backend target) within <30s from action.
- **FR-004**: System MUST provide an admin web interface for viewing active, expired, and upcoming access grants with filtering by status and date.
- **FR-005**: System MUST allow administrators to extend, revoke, and create new vouchers specifying duration and optional bandwidth constraints.
- **FR-006**: System MUST persist admin accounts securely and support creation of additional admin accounts after initial bootstrap.
- **FR-007**: System MUST store mapping selections of HA entities used for guest access decision logic.
- **FR-008**: System MUST expose an API endpoint to modify existing access grants (extend/revoke) and reflect changes in controller.
- **FR-009**: System MUST enforce themed presentation allowing configurable logo, color palette, and welcome message for portal page.
- **FR-010**: System MUST log all administrative actions (create/extend/revoke voucher, account creation) with timestamp and actor for audit.
- **FR-011**: System MUST support operation as Home Assistant addon AND as standalone container with equivalent configuration capabilities.
- **FR-012**: System MUST provide clear error message to guest when voucher invalid or expired without exposing internal system details.
- **FR-013**: System MUST handle controller communication failures by queuing intended changes and retrying until success or timeout threshold.
- **FR-014**: System MUST prevent duplicate grants for same voucher if multiple redemption attempts occur simultaneously.

*Assumptions: TP-Omada controller API offers endpoints for session authorization, revocation, and modification; standard HTTPS REST assumed.*

*Clarifications Needed:* None (defaults chosen for unspecified implementation specifics).

### Key Entities *(include if feature involves data)*

- **Voucher**: Represents a redeemable access token with fields: code, created timestamp, duration, optional bandwidth constraints, status (unused, active, expired, revoked), associated booking reference (optional).
- **Access Grant**: Active authorization object: device identifier (MAC/IP placeholder), start time, expiration time, voucher reference, controller grant ID, status.
- **Admin Account**: Credentials metadata: username, role, created timestamp, last login timestamp, active flag.
- **HA Rental Entity Mapping**: Configuration linking selected Home Assistant entity IDs to portal roles (e.g., booking status entity, stay start date entity, stay end date entity).
- **Audit Log Entry**: Action record: actor, action type, target entity ID, timestamp, outcome status.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: Guests redeem valid vouchers and obtain network access in under 60 seconds (from initial portal page load to authorization completion) for 95% of attempts.
- **SC-002**: Administrative actions (extend/revoke) propagate to controller within 30 seconds for 95% of actions.
- **SC-003**: Duplicate voucher redemption attempts result in single access grant creation (0% duplication rate in tests of 100 concurrent attempts).
- **SC-004**: Portal uptime (guest page + admin API responsiveness) ≥99% during monitored period excluding planned maintenance.
- **SC-005**: Audit log records 100% of admin actions with actor and timestamp traceable.
- **SC-006**: Entity mapping selection persists and is retrievable after restart with 100% consistency across 5 restart cycles.
