SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Admin UI Pages

**Feature Branch**: `005-admin-ui-pages`
**Created**: 2025-07-15
**Status**: Draft
**Input**: User description: "Build out missing admin UI pages — Dashboard, Grants, Vouchers, and verify Logout functionality"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Grants and Manage Access (Priority: P1)

As a portal administrator, I want to view all current access grants and be able to revoke or extend them so that I can manage who has network access in real time.

**Why this priority**: Grant management is the core operational task for a captive portal administrator. Without this page, admins must use the raw API to manage grants, which is impractical for daily operations. This delivers the highest day-to-day value.

**Independent Test**: Can be fully tested by navigating to the Grants page, verifying the grant list loads with correct data, filtering by status, extending a grant's duration, and revoking a grant. Delivers immediate value by enabling visual grant management.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they navigate to the Grants page, **Then** they see a table of all access grants showing MAC address, status, booking reference, voucher code, start time, end time, and available actions.
2. **Given** an authenticated admin viewing the Grants page, **When** they select a status filter (e.g., "Active"), **Then** the table updates to show only grants matching that status.
3. **Given** an authenticated admin viewing an active grant, **When** they choose to extend it and specify a duration, **Then** the grant's end time is updated and the page confirms the change.
4. **Given** an authenticated admin viewing an active or pending grant, **When** they choose to revoke it, **Then** the grant status changes to "Revoked" and the page confirms the action.
5. **Given** an authenticated admin, **When** the grant list is empty for a given filter, **Then** a clear "No grants found" message is displayed.

---

### User Story 2 - View Dashboard Overview (Priority: P2)

As a portal administrator, I want to see an at-a-glance dashboard when I log in so that I can quickly understand the current state of the captive portal — how many active grants exist, recent activity, and system status.

**Why this priority**: The Dashboard is the landing page after login and sets the context for all other admin tasks. It provides situational awareness but is not directly actionable, making it important but secondary to grant management.

**Independent Test**: Can be fully tested by logging in and navigating to the Dashboard, verifying that summary statistics (active grants count, pending grants count, available vouchers, integration count) and recent activity entries are displayed correctly.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they navigate to the Dashboard, **Then** they see summary statistics including active grant count, pending grant count, available voucher count, and integration count.
2. **Given** an authenticated admin on the Dashboard, **When** recent administrative actions have occurred (e.g., grant created, voucher redeemed), **Then** a recent activity feed shows the most recent entries with timestamp, action type, target, and acting admin.
3. **Given** an authenticated admin on the Dashboard, **When** there are no grants or vouchers in the system, **Then** the statistics display zero values gracefully rather than errors.

---

### User Story 3 - Create and Manage Vouchers (Priority: P3)

As a portal administrator, I want to create voucher codes and track their redemption status so that I can distribute time-limited network access to guests without manually creating grants.

**Why this priority**: Voucher management enables a self-service workflow where admins pre-generate codes and hand them to guests. This is valuable but depends on having the grant management foundation (P1) in place first, since redeemed vouchers create grants.

**Independent Test**: Can be fully tested by navigating to the Vouchers page, creating a new voucher with a specified duration, viewing the generated code, and verifying the voucher appears in the list with its status.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they navigate to the Vouchers page, **Then** they see a list of existing vouchers showing code, duration, status, creation date, and redemption details (if redeemed).
2. **Given** an authenticated admin on the Vouchers page, **When** they create a new voucher by specifying a duration in minutes, **Then** the system generates a voucher code and displays it to the admin for distribution.
3. **Given** an authenticated admin on the Vouchers page, **When** they create a voucher with an optional booking reference, **Then** the voucher is associated with that reference and it appears in the voucher list.
4. **Given** an authenticated admin viewing the Vouchers page, **When** a voucher has been redeemed by a guest, **Then** the voucher shows its redeemed status along with the associated grant information.
5. **Given** an authenticated admin on the Vouchers page, **When** the voucher list is empty, **Then** a clear "No vouchers found" message is displayed with a prompt to create one.

---

### User Story 4 - Logout Securely (Priority: P4)

As a portal administrator, I want to log out of the admin interface so that my session is terminated and no one else can use my browser to access admin functions.

**Why this priority**: Logout is a basic security function. It has a lower priority because the mechanism may already partially work (the nav bar form exists); this story ensures it is fully functional and tested end-to-end.

**Independent Test**: Can be fully tested by clicking the Logout button from any admin page, verifying the session is cleared, and confirming that subsequent attempts to access admin pages redirect to the login page.

**Acceptance Scenarios**:

1. **Given** an authenticated admin on any admin page, **When** they click the Logout button, **Then** their session is terminated and they are redirected to the login page.
2. **Given** a user who has just logged out, **When** they attempt to navigate directly to any admin page (e.g., Dashboard, Grants), **Then** they are redirected to the login page.
3. **Given** a user who has just logged out, **When** they press the browser's back button, **Then** they do not see cached admin content and are redirected to the login page.
4. **Given** any authenticated admin page or the Logout response, **When** the HTTP response is sent to the browser, **Then** it includes headers (or equivalent configuration) that prevent caching of admin content (for example, `Cache-Control: no-store, no-cache, must-revalidate`, `Pragma: no-cache`, and `Expires: 0`), so that after logout the browser back button cannot display stale admin content and this behavior can be verified by inspecting the response headers.

---

### Edge Cases

- What happens when an admin tries to revoke a grant that has already expired? The system should display a clear message that the grant is already expired and cannot be revoked.
- What happens when an admin tries to extend a revoked grant? The system should reject the extension and display an appropriate error message.
- What happens when the backend API is unreachable while the admin is on the Dashboard? The page should display an error state rather than crashing, showing a message like "Unable to load data."
- What happens when an admin creates a voucher while another admin simultaneously creates one? Each voucher should receive a unique code without conflicts.
- What happens when an admin navigates to a page via direct URL without authentication? They should be redirected to the login page.
- What happens when JavaScript is disabled? Forms with `method="POST"` should still function as a fallback for critical actions (revoke, create voucher, logout).

## Requirements *(mandatory)*

### Functional Requirements

#### Dashboard

- **FR-001**: System MUST serve the Dashboard page to authenticated administrators at the `/admin/dashboard` path.
- **FR-002**: Dashboard MUST display summary statistics: active grants count, pending grants count, available vouchers count, and configured integrations count.
- **FR-003**: Dashboard MUST display a recent activity feed showing the most recent administrative actions with timestamp, action type, target, and acting administrator.
- **FR-004**: Dashboard MUST handle the case where no data exists gracefully, displaying zero counts and an empty activity feed without errors.

#### Grants

- **FR-005**: System MUST serve the Grants management page to authenticated administrators at the `/admin/grants` path.
- **FR-006**: Grants page MUST display a table of all access grants with columns for MAC address, status, booking reference, voucher code, start time, end time, and actions.
- **FR-007**: Grants page MUST support filtering the grant list by status (e.g., Active, Pending, Expired, Revoked).
- **FR-008**: Grants page MUST allow administrators to extend an active grant's duration by specifying additional minutes.
- **FR-009**: Grants page MUST allow administrators to revoke an active or pending grant.
- **FR-010**: Extend and revoke actions MUST use form submissions with `method="POST"` as the primary mechanism, with optional progressive enhancement for a smoother experience.
- **FR-011**: Grants page MUST display confirmation feedback after a successful extend or revoke operation.
- **FR-012**: Grants page MUST display an appropriate error message when an extend or revoke operation fails (e.g., attempting to extend a revoked grant).

#### Vouchers

- **FR-013**: System MUST serve the Vouchers management page to authenticated administrators at the `/admin/vouchers` path.
- **FR-014**: Vouchers page MUST display a list of all vouchers showing code, duration, status, creation date, and redemption details.
- **FR-015**: Vouchers page MUST provide a form to create a new voucher by specifying at minimum the access duration in minutes.
- **FR-016**: Voucher creation form MUST support optional fields for booking reference.
- **FR-017**: After creating a voucher, the system MUST display the generated voucher code prominently so the administrator can copy or share it.
- **FR-018**: Vouchers page MUST show the redemption status of each voucher (unredeemed, redeemed) and link to the associated grant if redeemed.

#### Logout

- **FR-019**: The Logout button in the navigation bar MUST terminate the administrator's session when clicked.
- **FR-020**: After logout, the system MUST redirect the administrator to the login page.
- **FR-021**: After logout, attempts to access any admin page MUST redirect to the login page.

#### Cross-Cutting

- **FR-022**: All new admin pages MUST require administrator authentication; unauthenticated users MUST be redirected to the login page.
- **FR-023**: All new admin pages MUST include CSRF protection on state-changing operations.
- **FR-024**: All new pages MUST support ingress root path prefixing on all internal URLs and asset references.
- **FR-025**: All JavaScript MUST be loaded from external files; no inline scripts are permitted.
- **FR-026**: All new pages MUST follow the same visual design and navigation pattern as the existing Settings and Integrations pages.
- **FR-027**: All new source files MUST include the required SPDX license headers.

### Key Entities

- **Grant**: Represents an active network access authorization for a specific device. Key attributes: device identifier (MAC address), status (Pending, Active, Expired, Revoked), time window (start and end), optional booking reference, optional voucher code association, optional integration association.
- **Voucher**: Represents a pre-generated code that can be redeemed by a guest to create a grant. Key attributes: unique code, access duration, status (available, redeemed), creation timestamp, optional booking reference, redemption details.
- **Admin Session**: Represents an authenticated administrator's active login session. Key attributes: session identifier, associated admin identity, creation time.
- **Activity Log Entry**: Represents a recorded administrative action. Key attributes: timestamp, action type, target entity type and identifier, acting administrator.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All navigation links in the admin interface lead to working pages — zero broken links or error pages when an authenticated admin clicks any nav item.
- **SC-002**: An administrator can view, filter, extend, and revoke grants entirely through the web interface without needing direct API access, completing any single grant operation in under 30 seconds.
- **SC-003**: An administrator can create a new voucher and obtain the generated code within 15 seconds using the web interface.
- **SC-004**: An administrator can assess the current state of the portal (active grants, pending grants, available vouchers, recent activity) within 5 seconds of loading the Dashboard.
- **SC-005**: After clicking Logout, 100% of subsequent requests to admin pages redirect to the login page until the administrator logs in again.
- **SC-006**: All admin pages remain fully functional when accessed through Home Assistant ingress (root path prefixed URLs).
- **SC-007**: Core admin operations (revoke grant, create voucher, logout) remain functional even when JavaScript is disabled, via form POST fallbacks.

## Assumptions

- The existing admin authentication and session management system will be reused; no new authentication mechanism is required.
- The existing backend APIs for grants and vouchers are complete, tested, and will not require modification to support these UI pages.
- The existing `dashboard.html` and `grants_enhanced.html` templates are suitable starting points and follow the established design conventions, though they may need updates to align with final requirements.
- No voucher template currently exists; a new `vouchers.html` template will need to be created.
- The existing `admin.css` stylesheet provides sufficient styling classes (tables, badges, forms, buttons) for the new pages; only minor CSS additions may be needed.
- New external JavaScript files will be created for pages that need dynamic behavior (e.g., API fetching, progressive enhancement).
- The logout mechanism MUST call the `/api/admin/auth/logout` endpoint; if the backend currently exposes a different path (e.g., `/api/admin/logout`), this is a requirements gap that MUST be resolved by aligning the backend to this contract or updating this spec before implementation begins.
- Activity log data for the Dashboard's recent activity feed is available from an existing service or can be derived from existing data.
- The admin interface is used by a small number of administrators (typically 1-5), so high-concurrency optimization is not a concern.
