SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Voucher Management

**Feature Branch**: `007-voucher-management`
**Created**: 2025-07-14
**Status**: Draft
**Input**: User description: "Voucher lifecycle management — revoke, delete, and bulk operations for the existing vouchers page"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Revoke a Voucher (Priority: P1)

As an administrator, I need to revoke a voucher so that it can no longer be redeemed by guests. This is the most critical lifecycle action because it directly protects network access — if a voucher code is leaked or a guest's stay is cancelled, the admin must be able to immediately prevent further use.

**Why this priority**: Revoking a voucher is the primary security control. Without it, a compromised or cancelled voucher code remains valid indefinitely (until expiration), creating an uncontrolled access window. This is the minimum viable addition to voucher lifecycle management.

**Independent Test**: Can be fully tested by creating a voucher, clicking the revoke action on the vouchers page, and verifying the voucher status changes to "revoked" and can no longer be redeemed at the captive portal.

**Acceptance Scenarios**:

1. **Given** an unused voucher exists on the vouchers page, **When** the admin clicks the revoke button for that voucher, **Then** the voucher status changes to "revoked" and a confirmation message is displayed.
2. **Given** an active voucher (previously redeemed at least once) exists, **When** the admin revokes it, **Then** the voucher status changes to "revoked" and no further redemptions are accepted for that voucher code.
3. **Given** a voucher is already revoked, **When** the admin views the vouchers page, **Then** the revoke button for that voucher is disabled or hidden.
4. **Given** an expired voucher exists, **When** the admin views the vouchers page, **Then** the revoke button for that voucher is disabled or hidden (revocation is unnecessary for expired vouchers).
5. **Given** the admin clicks revoke on a voucher, **When** the operation completes, **Then** the page refreshes and preserves the admin's current position/context (no loss of scroll position or applied filters).

---

### User Story 2 - Delete a Voucher (Priority: P2)

As an administrator, I need to permanently remove unused vouchers from the system to keep the voucher list clean and manageable. Deletion is only permitted for vouchers that have never been redeemed, ensuring that audit history for used vouchers is preserved.

**Why this priority**: Deletion is a housekeeping feature that improves usability when the voucher list grows large. It is lower priority than revoke because unused vouchers pose no security risk — they simply add clutter. The restriction to unused vouchers ensures no audit trail is lost.

**Independent Test**: Can be fully tested by creating a voucher (without redeeming it), clicking the delete action, and verifying the voucher is completely removed from the list.

**Acceptance Scenarios**:

1. **Given** an unused voucher exists, **When** the admin clicks the delete button for that voucher, **Then** the voucher is permanently removed from the system and no longer appears in the voucher list.
2. **Given** a voucher has been redeemed at least once (active status), **When** the admin views the vouchers page, **Then** the delete button for that voucher is disabled or hidden.
3. **Given** a revoked voucher that was previously redeemed, **When** the admin views the vouchers page, **Then** the delete button is disabled or hidden (redeemed vouchers cannot be deleted regardless of current status).
4. **Given** a revoked voucher that was never redeemed (revoked while still unused), **When** the admin clicks delete, **Then** the voucher is permanently removed from the system.
5. **Given** the admin clicks delete on an unused voucher, **When** the operation completes, **Then** a confirmation message is displayed and the voucher list updates accordingly.

---

### User Story 3 - Bulk Voucher Operations (Priority: P3)

As an administrator managing a large number of vouchers (e.g., for a hotel or event), I need to select multiple vouchers at once and apply revoke or delete actions in bulk, rather than acting on each voucher one at a time.

**Why this priority**: Bulk operations are a productivity enhancement. The core functionality (revoke/delete) works without them, but they become essential when managing dozens or hundreds of vouchers. This is lower priority because admins can still achieve the same result through individual actions.

**Independent Test**: Can be fully tested by creating several vouchers, selecting multiple via checkboxes, applying a bulk action, and verifying all selected vouchers are affected.

**Acceptance Scenarios**:

1. **Given** multiple unused vouchers exist, **When** the admin selects three vouchers using checkboxes and clicks "Delete Selected", **Then** all three vouchers are permanently removed and a summary message indicates how many were deleted.
2. **Given** multiple vouchers in various statuses exist, **When** the admin selects five vouchers and clicks "Revoke Selected", **Then** only the eligible vouchers (unused and active) are revoked, and a summary message indicates how many were revoked and how many were skipped.
3. **Given** the admin selects a mix of unused and redeemed vouchers, **When** they click "Delete Selected", **Then** only the unused vouchers are deleted, the redeemed vouchers are skipped, and a summary message explains the outcome (e.g., "Deleted 2 vouchers, skipped 3 (already redeemed)").
4. **Given** no vouchers are selected, **When** the admin clicks a bulk action button, **Then** the system displays a message asking the admin to select at least one voucher.
5. **Given** the voucher list has a "select all" checkbox, **When** the admin clicks it, **Then** all visible vouchers are selected for bulk action.

---

### Edge Cases

- What happens when an admin attempts to revoke a voucher that was concurrently revoked by another admin? The operation should be idempotent — no error is shown, and the voucher remains revoked.
- What happens when an admin attempts to delete a voucher that was redeemed between page load and the delete action? The system should reject the deletion and display an error explaining the voucher has been redeemed and can no longer be deleted.
- What happens when a bulk operation includes vouchers that have changed status since the page was loaded? The system should process each voucher individually, skipping ineligible ones, and report a summary of successes and skips.
- What happens when the admin tries to delete a voucher that no longer exists (e.g., deleted by another admin)? The system should handle this gracefully with an appropriate message rather than an error page.
- What happens when a voucher is revoked while a guest is in the process of redeeming it? The redemption should fail with a clear message that the voucher is no longer valid. Existing access grants created from prior redemptions of that voucher are not affected.

## Requirements *(mandatory)*

### Functional Requirements

#### Revoke

- **FR-001**: System MUST allow administrators to revoke individual vouchers that are in "unused" or "active" status.
- **FR-002**: System MUST change the voucher status to "revoked" when a revoke action is performed.
- **FR-003**: System MUST prevent redemption of revoked vouchers at the captive portal.
- **FR-004**: System MUST treat revoking an already-revoked voucher as a no-op (idempotent) without displaying an error.
- **FR-005**: System MUST NOT allow revoking expired vouchers (revocation is unnecessary and would be misleading).

#### Delete

- **FR-006**: System MUST allow administrators to delete vouchers that have never been redeemed (redeemed_count is zero).
- **FR-007**: System MUST permanently remove deleted vouchers from the system with no option to undo.
- **FR-008**: System MUST prevent deletion of vouchers that have been redeemed at least once, regardless of current status.
- **FR-009**: System MUST allow deletion of revoked vouchers that were never redeemed.
- **FR-010**: System MUST reject a delete request if the voucher was redeemed between page load and action submission, displaying an explanatory error message.

#### Bulk Operations

- **FR-011**: System MUST provide a mechanism to select multiple vouchers on the vouchers page (e.g., checkboxes).
- **FR-012**: System MUST provide a "select all" control that selects all visible vouchers.
- **FR-013**: System MUST allow bulk revoke of selected vouchers, processing each individually and skipping ineligible ones.
- **FR-014**: System MUST allow bulk delete of selected vouchers, processing each individually and skipping ineligible ones (redeemed vouchers).
- **FR-015**: System MUST display a summary after bulk operations indicating how many vouchers were affected and how many were skipped, with reasons.
- **FR-016**: System MUST require at least one voucher to be selected before allowing a bulk action.

#### UI & Interaction

- **FR-017**: System MUST display revoke and delete action controls for each voucher on the vouchers page, with appropriate enabled/disabled states based on voucher eligibility.
- **FR-018**: System MUST follow the Post/Redirect/Get pattern for all voucher management actions, consistent with the existing grants page.
- **FR-019**: System MUST validate CSRF tokens on all voucher management actions.
- **FR-020**: System MUST log all revoke and delete actions for audit purposes, including the administrator who performed the action and the voucher(s) affected.
- **FR-021**: System MUST display confirmation feedback (success or error) after each action via redirect query parameters, consistent with existing page patterns.

### Key Entities

- **Voucher**: A redeemable access code with a lifecycle status (unused → active → expired, or revoked at any point). Key attributes: code (unique identifier), duration, status, redemption count, booking reference, creation timestamp. The status determines which management actions are available.
- **VoucherStatus**: The lifecycle state of a voucher — unused (never redeemed), active (redeemed at least once), expired (past duration), or revoked (manually cancelled by admin). Transitions: unused→active (on redemption), unused→revoked (admin action), active→revoked (admin action), unused/active→expired (time-based). Revoked and expired are terminal states.
- **Bulk Operation Result**: A summary of a bulk action outcome — total selected, number successfully processed, number skipped, and reasons for skips. Communicated to the admin via feedback messages after the action completes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can revoke a single voucher in under 3 seconds (from click to confirmation message).
- **SC-002**: Administrators can delete a single unused voucher in under 3 seconds (from click to confirmation message).
- **SC-003**: Administrators can select and bulk-revoke 20 vouchers in under 10 seconds (from first selection to confirmation message).
- **SC-004**: 100% of revoked vouchers are immediately rejected when a guest attempts redemption.
- **SC-005**: 100% of deleted vouchers are completely removed from the system with no residual data visible to administrators.
- **SC-006**: Bulk operations correctly skip ineligible vouchers and report accurate summaries 100% of the time.
- **SC-007**: All voucher management actions produce an audit log entry with the administrator identity and action details.

## Assumptions

- The existing admin authentication and authorization system (require_admin dependency) will be reused — no new permission model is needed for these actions.
- The existing VoucherStatus enum already includes the "revoked" status, so no data model changes are needed for revocation.
- The existing CSRF protection mechanism used by the vouchers create and grants extend/revoke actions will be reused.
- The existing audit logging service used by grants and voucher creation will be extended to cover revoke and delete actions.
- Voucher deletion is a hard delete (permanent removal), not a soft delete. Audit logs capture the action, but the voucher record itself is removed.
- The vouchers page already loads and displays vouchers — bulk operations add selection UI on top of the existing table without redesigning the page layout.
- This feature does not add status filtering to the vouchers page; that may be addressed separately.
- Existing access grants created from a redeemed voucher are not affected when that voucher is subsequently revoked — grant lifecycle is managed independently on the grants page.
