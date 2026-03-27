SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Integrations Auto-Detection

**Feature Branch**: `006-integrations-auto-detect`
**Created**: 2025-07-14
**Status**: Draft
**Input**: User description: "Auto-detect available Rental Control integrations from Home Assistant, present them as a pick-list with entity state info, and fall back to manual entry if the HA API is unavailable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Select Integration from Auto-Detected List (Priority: P1)

An admin navigates to the integrations page to add a new Rental Control integration. Instead of guessing or remembering an obscure integration identifier, they see a dropdown populated with all available Rental Control integrations discovered from Home Assistant. Each entry in the list shows the integration's friendly name and current status. The admin selects the correct one and saves.

**Why this priority**: This is the core value of the feature — eliminating the confusing free-text input and replacing it with an intuitive pick-list. Without this, the remaining stories have no foundation.

**Independent Test**: Can be fully tested by visiting the integrations page with at least one Rental Control integration configured in Home Assistant, confirming the dropdown appears with the correct entries, and successfully saving a selection.

**Acceptance Scenarios**:

1. **Given** the admin is on the integrations page and Home Assistant has two Rental Control integrations configured, **When** the page loads, **Then** a dropdown/pick-list displays both integrations with their friendly names.
2. **Given** the admin sees the auto-detected integration list, **When** they select an integration and click save, **Then** the system creates a new integration configuration using the selected integration's identifier.
3. **Given** the admin sees the auto-detected integration list, **When** one of the integrations is already configured in the captive portal, **Then** that integration is visually marked as "already added" and cannot be selected again.

---

### User Story 2 - View Entity State Details Before Selecting (Priority: P2)

An admin has multiple Rental Control integrations (e.g., one per property or unit). They need to tell them apart before adding one. The pick-list shows contextual information for each integration — such as the number of active bookings, the calendar entity's current state, and key attributes — so the admin can confidently choose the right one without leaving the page.

**Why this priority**: This enhances the P1 pick-list with disambiguation details. Properties may have similar names, and showing live state info prevents adding the wrong integration. However, the basic pick-list (P1) is still usable without these details.

**Independent Test**: Can be tested by loading the integrations page when Rental Control integrations have active bookings. Verify that each list entry shows the entity's current state and at least one identifying attribute (e.g., active booking count or next check-in).

**Acceptance Scenarios**:

1. **Given** a Rental Control integration has two active bookings, **When** the admin views the pick-list, **Then** the entry for that integration shows the number of active bookings.
2. **Given** a Rental Control integration has no active bookings, **When** the admin views the pick-list, **Then** the entry shows an "idle" or "no active bookings" indicator.
3. **Given** the entity state contains calendar attributes (e.g., next event summary, start date), **When** the admin views the pick-list, **Then** the entry shows these relevant attributes as context.

---

### User Story 3 - Fall Back to Manual Entry (Priority: P3)

An admin needs to add an integration, but the Home Assistant API is temporarily unreachable (e.g., HA is restarting, the supervisor is unresponsive, or network connectivity is interrupted). The system gracefully notifies the admin that auto-detection is unavailable and provides a manual text input field as a fallback, identical in behavior to the current implementation.

**Why this priority**: This ensures the feature degrades gracefully rather than blocking the admin. It is lower priority because HA API availability is the normal operating condition for this addon, but resilience is important for real-world reliability.

**Independent Test**: Can be tested by simulating an unreachable HA API (e.g., invalid token, network timeout) and verifying the integrations page still allows manual entry with an appropriate notification message.

**Acceptance Scenarios**:

1. **Given** the Home Assistant API is unreachable, **When** the admin loads the integrations page, **Then** the system displays a notification explaining that auto-detection is unavailable and shows a manual text input field.
2. **Given** the admin sees the manual entry fallback, **When** they type an integration identifier and save, **Then** the system creates the integration configuration exactly as the current implementation does.
3. **Given** the Home Assistant API was unreachable but becomes available again, **When** the admin refreshes the page, **Then** the auto-detected pick-list appears in place of the manual entry field.

---

### User Story 4 - Refresh Available Integrations (Priority: P4)

An admin has the integrations page open and realizes they need to add a Rental Control integration to Home Assistant first. After configuring the new integration in HA, they return to the captive portal's integrations page and trigger a refresh to see the newly added integration in the pick-list without reloading the entire page.

**Why this priority**: This is a convenience enhancement. Admins can always do a full page reload to re-trigger auto-detection, but a dedicated refresh action is a smoother experience when iterating on setup.

**Independent Test**: Can be tested by loading the integrations page, adding a new Rental Control integration in HA, clicking the refresh control, and verifying the new integration appears in the list.

**Acceptance Scenarios**:

1. **Given** the admin is on the integrations page with the pick-list displayed, **When** they click a refresh/reload control, **Then** the system re-queries Home Assistant and updates the pick-list with any newly available integrations.
2. **Given** the admin clicks refresh, **When** the re-query is in progress, **Then** the system shows a loading indicator so the admin knows the request is being processed.

---

### Edge Cases

- What happens when Home Assistant has zero Rental Control integrations? The system displays a helpful empty state message explaining that no Rental Control integrations were found and suggests the admin install one in Home Assistant first, while still offering the manual entry fallback.
- What happens when the HA API responds but returns an error (e.g., 401 Unauthorized, 500 Internal Server Error)? The system treats this as "unavailable" and falls back to manual entry, displaying a constrained error notification (for example, HTTP status code and a short, human-readable reason) while logging full error details server-side for troubleshooting. The UI MUST NOT expose sensitive information such as tokens, internal URLs, or raw response bodies.
- What happens when a previously auto-detected integration is removed from Home Assistant after being added to the captive portal? The already-configured integration in the captive portal remains functional (it relies on polling, which will naturally detect staleness). The removed integration no longer appears in the pick-list for new additions.
- What happens when the HA API is slow to respond (e.g., >5 seconds)? The page displays a loading indicator during detection. If the request exceeds a reasonable timeout (e.g., 10 seconds), the system falls back to manual entry with a timeout notification.
- What happens when an admin has many Rental Control integrations (e.g., 20+)? The pick-list remains usable with a scrollable list. Entity state details help the admin quickly identify the correct integration.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST query Home Assistant to discover all available Rental Control integrations when the integrations page is loaded.
- **FR-002**: System MUST present discovered integrations as a selectable pick-list (dropdown or equivalent), replacing the free-text input as the primary entry method.
- **FR-003**: System MUST display each discovered integration's friendly name as the primary label in the pick-list.
- **FR-004**: System MUST display contextual entity state information alongside each integration in the pick-list, including current state (active/idle) and active booking count.
- **FR-005**: System MUST display relevant calendar attributes (e.g., next event summary, upcoming check-in date) for each discovered integration when available.
- **FR-006**: System MUST visually indicate integrations that are already configured in the captive portal and prevent duplicate additions.
- **FR-007**: System MUST fall back to a manual text entry field when the Home Assistant API is unreachable, returns an error, or times out.
- **FR-008**: System MUST display a clear, user-friendly notification explaining why auto-detection is unavailable when falling back to manual entry, including the nature of the failure (e.g., timeout, authentication error, connection refused), and MUST NOT expose secrets (such as tokens) or verbose stack traces; detailed diagnostic information MUST be written to logs instead of shown in the UI.
- **FR-009**: System MUST provide a refresh control that re-queries Home Assistant for available integrations without requiring a full page reload.
- **FR-010**: System MUST show a loading indicator while the integration discovery query is in progress.
- **FR-011**: System MUST use the integration identifier discovered from Home Assistant as the stored `integration_id` value, ensuring consistency with the existing polling and event processing system.
- **FR-012**: System MUST continue to support all existing integration configuration fields (identifier attribute, checkout grace period) regardless of whether the integration was selected from the pick-list or entered manually.

### Key Entities

- **Discovered Integration**: Represents a Rental Control integration found in Home Assistant. Key attributes: entity identifier, friendly name, current state (active/idle), active booking count, calendar attributes (next event, upcoming dates). This is a transient entity — not persisted, only used during the selection flow.
- **Integration Configuration**: The existing persisted record of a configured integration (maps to the current HAIntegrationConfig). Extended in this feature only in how its `integration_id` is populated (from pick-list selection rather than manual text entry).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can add a new Rental Control integration in under 30 seconds from page load to saved configuration, compared to the current workflow that requires prior knowledge of the integration identifier.
- **SC-002**: 95% of users select the correct integration on their first attempt when using the auto-detected pick-list, eliminating typo and guesswork errors.
- **SC-003**: Zero integration configurations are created with invalid or misspelled identifiers when using the auto-detected pick-list.
- **SC-004**: When the Home Assistant API is unavailable, the manual entry fallback is presented within 10 seconds, ensuring the admin is never blocked from configuring integrations.
- **SC-005**: The integration discovery query completes and populates the pick-list within 5 seconds under normal operating conditions.
- **SC-006**: 100% of Rental Control integrations present in Home Assistant appear in the auto-detected pick-list (no false negatives).

## Assumptions

- The addon runs in a Home Assistant supervised environment where an authorization mechanism (for example, a Supervisor-provided API token) is made available to the addon at runtime and does not require user configuration. This assumption typically holds when the addon's configuration includes `homeassistant_api: true`, which permits access to the Home Assistant REST API.
- Rental Control integrations expose calendar entities following a discoverable naming pattern (e.g., `calendar.rental_control_*`), which can be enumerated by querying Home Assistant for available entities.
- The admin has already installed and configured at least one Rental Control integration in Home Assistant before using the auto-detection feature. If none exist, the system guides them appropriately.
- The existing service layer for communicating with Home Assistant can be extended to support integration discovery without requiring new external dependencies.
- The existing integration configuration workflow (identifier attribute selection, checkout grace period) remains unchanged — only the integration ID entry method is enhanced.
- The addon has reliable network connectivity to the Home Assistant Supervisor API under normal operating conditions. The fallback to manual entry is for exceptional circumstances, not the default experience.
- Entity state information (bookings, calendar attributes) is available in real-time from Home Assistant and does not require additional integration-specific queries beyond the existing communication capabilities.
