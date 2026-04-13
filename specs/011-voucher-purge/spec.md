# Feature Specification: Voucher Auto-Purge and Admin Purge

**Feature Branch**: `011-voucher-purge`
**Created**: 2025-07-22
**Status**: Draft
**Input**: User description: "Automatically purge expired and revoked vouchers after 30 days, and provide an admin UI for manually purging expired/revoked vouchers older than N days (where 0 means all expired or revoked vouchers regardless of age)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Cleanup of Old Vouchers (Priority: P1)

As a system administrator, I want expired and revoked vouchers to be automatically removed from the database after a retention period so that the voucher list stays manageable and the database does not grow unbounded over time.

The system runs a background cleanup process that identifies vouchers in EXPIRED or REVOKED status whose terminal state was reached more than 30 days ago, and permanently deletes them. This happens without any admin intervention.

**Why this priority**: Database growth is the core problem this feature solves. Without automatic cleanup, the voucher table grows indefinitely, degrading admin page load times and consuming storage. This is the foundational capability — even without the manual purge UI, automatic cleanup delivers the primary value.

**Independent Test**: Can be fully tested by creating vouchers, transitioning them to EXPIRED/REVOKED, advancing time past the 30-day retention window, triggering the background process, and verifying the vouchers are removed from the database.

**Acceptance Scenarios**:

1. **Given** a voucher has been in EXPIRED status for more than 30 days, **When** the auto-purge process runs, **Then** the voucher is permanently deleted from the database.
2. **Given** a voucher has been in REVOKED status for more than 30 days, **When** the auto-purge process runs, **Then** the voucher is permanently deleted from the database.
3. **Given** a voucher has been in EXPIRED status for exactly 29 days, **When** the auto-purge process runs, **Then** the voucher is NOT deleted (retention period not yet reached).
4. **Given** a voucher is in ACTIVE or UNUSED status, **When** the auto-purge process runs, **Then** the voucher is never deleted regardless of age.
5. **Given** the auto-purge process deletes vouchers, **When** the deletion completes, **Then** the operation is recorded in the audit trail with the count of purged vouchers and the retention threshold used.
6. **Given** the auto-purge process runs but finds no vouchers eligible for purging, **When** the process completes, **Then** no error occurs and the system continues normally.

---

### User Story 2 - Admin Manual Purge of Old Vouchers (Priority: P2)

As an administrator, I want to manually purge expired and revoked vouchers older than a number of days I specify so that I can perform ad-hoc cleanup when needed — for example, before an audit, after a busy season, or to immediately reclaim space.

The admin navigates to the vouchers page, enters a minimum age in days (N), and initiates a purge. The system shows how many vouchers will be affected, asks for confirmation, and then deletes matching vouchers. Setting N=0 purges ALL expired and revoked vouchers regardless of when they reached that status.

**Why this priority**: Manual purge gives admins control beyond the automatic process. It depends on the same underlying purge logic as auto-purge (P1) but adds UI interaction, confirmation flow, and parameterized age threshold. Valuable but not essential — automatic cleanup alone keeps the system healthy.

**Independent Test**: Can be fully tested by navigating to the voucher admin page, entering an age threshold, confirming the purge, and verifying the correct vouchers are removed and the result is displayed.

**Acceptance Scenarios**:

1. **Given** the admin is on the vouchers page, **When** the admin enters N=0 and initiates purge, **Then** the system identifies ALL vouchers in EXPIRED or REVOKED status for deletion.
2. **Given** the admin enters N=14, **When** the purge is initiated, **Then** only EXPIRED or REVOKED vouchers whose terminal status was reached more than 14 days ago are deleted.
3. **Given** the admin initiates a purge, **When** the system calculates matching vouchers, **Then** a confirmation summary is displayed showing the count of vouchers that will be purged before the action is executed.
4. **Given** the admin confirms the purge, **When** the deletion completes, **Then** the admin sees a success message with the number of vouchers purged.
5. **Given** the admin initiates a purge but no vouchers match the criteria, **When** the purge completes, **Then** the admin sees a message indicating zero vouchers were eligible for purging.
6. **Given** the admin performs a manual purge, **When** the action completes, **Then** the operation is recorded in the audit trail with the admin's identity, the age threshold used, and the count of vouchers purged.

---

### User Story 3 - Status Transition Timestamp Tracking (Priority: P1)

As the system, I need to reliably know when each voucher entered its terminal status (EXPIRED or REVOKED) so that age-based purging can be accurately calculated.

Currently the voucher model does not track when a status transition occurred. A new timestamp field must record the moment a voucher transitions to EXPIRED or REVOKED. For existing vouchers already in a terminal status that lack this timestamp, a reasonable fallback must be used (e.g., the voucher's computed expiration time for EXPIRED vouchers, or the current migration time).

**Why this priority**: This is a prerequisite for both auto-purge and manual purge — without knowing when a voucher became expired or revoked, age-based purging cannot function correctly. This must be implemented alongside or before the purge logic.

**Independent Test**: Can be tested by transitioning a voucher to EXPIRED or REVOKED and verifying the transition timestamp is recorded. Can also be tested by running a migration and verifying existing terminal vouchers receive a reasonable fallback timestamp.

**Acceptance Scenarios**:

1. **Given** an ACTIVE voucher whose duration has elapsed, **When** the system transitions it to EXPIRED, **Then** the transition timestamp is recorded as the current time.
2. **Given** an admin revokes an ACTIVE voucher, **When** the voucher status changes to REVOKED, **Then** the transition timestamp is recorded as the current time.
3. **Given** existing EXPIRED vouchers in the database that lack a transition timestamp (pre-migration), **When** a data migration runs, **Then** those vouchers receive a fallback transition timestamp derived from their computed expiration time.
4. **Given** existing REVOKED vouchers in the database that lack a transition timestamp (pre-migration), **When** a data migration runs, **Then** those vouchers receive a fallback transition timestamp (e.g., set to the migration execution time or a reasonable estimate).
5. **Given** a voucher already in EXPIRED status, **When** the system processes it again during stale-voucher expiration, **Then** the existing transition timestamp is not overwritten.

---

### User Story 4 - Associated Data Handling During Purge (Priority: P2)

As a system administrator, I want purged voucher data to be handled consistently so that related records (access grants, audit logs) are treated appropriately when a voucher is permanently deleted.

**Why this priority**: Data integrity must be preserved during purge operations. Access grants reference vouchers, so deleting a voucher without handling grants could cause data inconsistencies. This is tightly coupled with the purge implementation.

**Independent Test**: Can be tested by purging a voucher that has associated access grants and audit log entries, then verifying the expected behavior for each related record type.

**Acceptance Scenarios**:

1. **Given** a voucher being purged has associated access grant records, **When** the voucher is deleted, **Then** the voucher reference on those grants is cleared (set to null) so the grant records are preserved as historical data but no longer reference the deleted voucher.
2. **Given** a voucher being purged has associated audit log entries, **When** the voucher is deleted, **Then** the audit log entries are preserved unchanged (audit logs are never deleted by voucher purge — they follow their own independent retention policy).
3. **Given** a voucher being purged has no associated access grants, **When** the voucher is deleted, **Then** the deletion succeeds without error.

---

### Edge Cases

- What happens when the auto-purge process runs concurrently with an admin manual purge targeting the same vouchers? The system should handle this gracefully — double-deletion of already-removed vouchers should not cause errors.
- What happens if a voucher is in EXPIRED status but has an access grant that is still ACTIVE (clock skew or edge case)? The purge should only consider the voucher's own status and age, not the grant status — but this scenario should be logged as a warning.
- What happens when the database contains thousands of expired/revoked vouchers eligible for purge? The purge should process efficiently without causing noticeable admin UI delays or database lock contention.
- What happens if the admin enters a negative number for the age threshold? The system should reject invalid input and display a validation error.
- What happens to vouchers that were EXPIRED and then never transitioned (legacy data without a transition timestamp and no fallback derivable)? The migration must handle all existing records — no voucher should be left without a usable age reference.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically delete vouchers in EXPIRED or REVOKED status whose terminal-status timestamp is older than the configured retention period (default: 30 days).
- **FR-002**: System MUST run the auto-purge process at least once per day, triggered either as part of an existing background loop or lazily on admin page load.
- **FR-003**: System MUST record a transition timestamp on the voucher whenever its status changes to EXPIRED or REVOKED.
- **FR-004**: System MUST provide a data migration that backfills transition timestamps for existing EXPIRED and REVOKED vouchers using reasonable fallback values.
- **FR-005**: System MUST provide an admin UI control on the vouchers page that allows the admin to initiate a manual purge of expired/revoked vouchers older than N days.
- **FR-006**: System MUST accept N=0 as a valid input for manual purge, meaning all expired and revoked vouchers are purged regardless of age.
- **FR-007**: System MUST validate the admin-provided age threshold input (non-negative integer) and display a clear error message for invalid input.
- **FR-008**: System MUST display a confirmation summary showing the count of vouchers that will be purged before executing the manual purge action.
- **FR-009**: System MUST display a result message to the admin after a manual purge completes, indicating the number of vouchers deleted.
- **FR-010**: System MUST record all purge operations (both automatic and manual) in the audit trail, including the actor (system or admin username), the age threshold, and the count of vouchers purged.
- **FR-011**: System MUST clear (nullify) the voucher reference on associated access grant records when a voucher is purged, preserving the grant records themselves as historical data.
- **FR-012**: System MUST NOT delete or modify audit log entries when a voucher is purged — audit logs follow their own independent retention policy.
- **FR-013**: System MUST NOT purge vouchers in UNUSED or ACTIVE status under any circumstances.
- **FR-014**: System MUST handle concurrent purge operations gracefully — if two purge processes target the same vouchers, no errors should result from attempting to delete already-removed records.

### Key Entities

- **Voucher**: Redeemable access code with a lifecycle status (UNUSED → ACTIVE → EXPIRED/REVOKED). Gains a new transition timestamp field that records when the voucher entered its terminal status. Primary key is `code`.
- **Access Grant**: Network authorization record linked to a voucher by voucher code. When a voucher is purged, the grant's voucher reference is nullified but the grant record itself is preserved for historical purposes.
- **Audit Log**: Immutable record of administrative actions. References vouchers by target ID (string, not a foreign key). Never deleted by voucher purge. New purge actions are logged as additional entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After auto-purge runs, zero vouchers remain in EXPIRED or REVOKED status with a terminal-status age exceeding the retention period.
- **SC-002**: Admin can complete a manual purge (enter threshold, confirm, see result) in under 30 seconds from the vouchers page.
- **SC-003**: Auto-purge process completes within 10 seconds for databases containing up to 10,000 expired/revoked vouchers.
- **SC-004**: 100% of purge operations (automatic and manual) produce a corresponding audit log entry.
- **SC-005**: Zero data integrity errors occur after purge — no orphaned foreign key references, no broken grant records.
- **SC-006**: All existing EXPIRED and REVOKED vouchers receive a transition timestamp after the data migration, with zero records left without a usable age reference.

## Assumptions

- The default auto-purge retention period of 30 days is acceptable and does not need to be configurable by the admin in this initial version. A future enhancement could expose this as an admin setting.
- The auto-purge can run lazily on admin page load (following the existing pattern used by `expire_stale_vouchers()`) rather than requiring a dedicated background scheduler. This is sufficient because admin pages are loaded regularly in typical usage.
- Access grants associated with purged vouchers should be preserved (with the voucher reference nullified) rather than cascade-deleted, because grants serve as historical records of network access for compliance and troubleshooting.
- Audit log entries are never deleted by voucher purge — they have their own independent retention policy managed by the existing `AuditCleanupService`.
- For the migration backfill of existing EXPIRED vouchers without a transition timestamp, using the voucher's computed expiration time (`activated_utc + duration_minutes`) is an acceptable approximation of when the voucher actually expired.
- For the migration backfill of existing REVOKED vouchers without a transition timestamp, using the migration execution time is acceptable since the actual revocation time is not recoverable.
- The manual purge UI is integrated into the existing vouchers admin page rather than being a separate page, keeping the admin workflow consolidated.
- The confirmation step for manual purge can be implemented as a two-step form flow (count preview → confirm deletion) within the same page, following the existing Post/Redirect/Get pattern used elsewhere in the admin UI.
