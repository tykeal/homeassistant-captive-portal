# Research: Voucher Auto-Purge and Admin Purge

**Feature Branch**: `011-voucher-purge`
**Date**: 2025-07-22

## Research Questions & Findings

### R1: How should the `status_changed_utc` field be stored and migrated?

**Decision**: Add a nullable `datetime` column `status_changed_utc` to the `voucher` table, following the exact pattern of the existing `activated_utc` migration.

**Rationale**:
- The codebase already has four lightweight migration functions in `database.py` that handle adding columns and backfilling data. This is the established pattern — no external migration framework (Alembic) is used.
- A nullable `Optional[datetime]` field is consistent with other optional timestamp fields on the model (`activated_utc`, `last_redeemed_utc`).
- SQLModel/SQLAlchemy handles the column definition; the migration function uses raw SQL for ALTER TABLE + backfill.

**Alternatives considered**:
- **Alembic migrations**: Rejected — the project deliberately uses lightweight inline migrations. Introducing Alembic would add complexity and a new dependency for a single column addition.
- **Separate `voucher_status_history` table**: Rejected — the spec only requires knowing *when* the terminal status was reached, not a full status change history. A single field is simpler and sufficient.
- **Computed column from `expires_utc`**: Rejected — this only works for EXPIRED vouchers, not REVOKED ones. A dedicated field handles both uniformly.

**Backfill strategy**:
- EXPIRED vouchers without `status_changed_utc`: Use `activated_utc + duration_minutes` (the computed expiration time). This matches the spec assumption that the actual expiration time is an acceptable approximation.
- REVOKED vouchers without `status_changed_utc`: Use the migration execution timestamp (`datetime.now(timezone.utc)`). The actual revocation time is not recoverable from existing data, per spec assumption.
- UNUSED/ACTIVE vouchers: Leave `status_changed_utc` as NULL — they have not reached a terminal status.

---

### R2: Where should the purge logic live — in `VoucherService` or a new service?

**Decision**: Create a new `VoucherPurgeService` in `addon/src/captive_portal/services/voucher_purge_service.py`.

**Rationale**:
- `VoucherService` handles individual voucher lifecycle operations (create, redeem, revoke, delete, expire). The purge feature is a bulk cleanup operation with different concerns (retention policy, batch deletion, grant nullification).
- The project already has `CleanupService` for event cleanup — a separate `VoucherPurgeService` follows this established pattern.
- Separation keeps `VoucherService` under the cyclomatic complexity limit (constitution principle I).

**Alternatives considered**:
- **Add methods to VoucherService**: Rejected — `VoucherService` already has 5+ methods. Adding purge logic (count, delete, grant handling) would push toward complexity limits and mix concerns.
- **Add to CleanupService**: Rejected — `CleanupService` is specifically for Rental Control events, not vouchers. Combining unrelated cleanup domains would violate single-responsibility.
- **Repository-only (no service)**: Rejected — purge involves cross-entity coordination (vouchers + grants + audit) which belongs in a service layer, not a repository.

---

### R3: How should access grant voucher references be nullified during purge?

**Decision**: Use a single batch SQL UPDATE statement to set `voucher_code = NULL` for all grants referencing the vouchers being purged, executed *before* the voucher DELETE statement, within the same transaction.

**Rationale**:
- SQLite enforces foreign key constraints. Deleting a voucher that has grants with a non-null `voucher_code` FK would violate the constraint. Nullifying first is necessary.
- A batch UPDATE is efficient — one SQL statement regardless of how many grants are affected.
- Running within the same transaction ensures atomicity: if the DELETE fails, the nullification is rolled back too.

**Alternatives considered**:
- **CASCADE DELETE on FK**: Rejected — the spec explicitly requires grants to be *preserved* with the voucher reference cleared, not deleted.
- **SET NULL via SQLAlchemy FK `ondelete`**: Considered — this would work if the FK constraint is defined with `ON DELETE SET NULL`. However, SQLite does not support `ALTER TABLE ... ALTER COLUMN` to retroactively change FK behavior on existing tables, and the existing FK definition does not include `ON DELETE SET NULL`. Explicit pre-delete nullification is more portable and explicit.
- **Row-by-row nullification**: Rejected — unnecessary overhead. Batch UPDATE is both simpler and faster.

---

### R4: How should the auto-purge be triggered?

**Decision**: Trigger auto-purge lazily on admin voucher page load, immediately after the existing `expire_stale_vouchers()` call in the `list_vouchers_admin` route handler.

**Rationale**:
- The spec explicitly assumes lazy triggering on admin page load (Assumptions section): "The auto-purge can run lazily on admin page load (following the existing pattern used by `expire_stale_vouchers()`)."
- The existing `list_vouchers_admin` GET handler already calls `expire_stale_vouchers()` to transition stale ACTIVE→EXPIRED before rendering. Adding a purge step after expiration is a natural extension of this pattern.
- No need for a background scheduler, cron job, or separate task queue — this keeps the architecture simple and consistent.

**Alternatives considered**:
- **Dedicated background scheduler (APScheduler, Celery)**: Rejected — adds significant complexity and new dependencies for a single-instance SQLite application. Overkill for this scale.
- **Startup-only purge**: Rejected — the add-on may run for weeks without restart. Purging only on startup would not satisfy the "at least once per day" requirement (FR-002).
- **Separate admin endpoint for auto-purge**: Rejected — adds an unnecessary endpoint. The lazy approach is simpler and matches the existing pattern.

---

### R5: How should the manual purge confirmation flow work?

**Decision**: Implement a two-step flow using two POST endpoints following the existing Post/Redirect/Get pattern:
1. **POST `/admin/vouchers/purge-preview`**: Accepts `min_age_days` from the form, queries the count of eligible vouchers, and redirects to the voucher page with the count and threshold displayed in a confirmation banner.
2. **POST `/admin/vouchers/purge-confirm`**: Accepts `min_age_days` (carried via hidden field), executes the purge, and redirects with a success/result message.

**Rationale**:
- The existing admin UI uses Post/Redirect/Get for all mutating actions (create, revoke, delete, bulk operations). The purge flow follows this same pattern.
- The two-step flow satisfies FR-008 (show confirmation count) and FR-009 (show result count).
- Using query parameters for feedback messages (`success`, `error`, `purge_preview_count`, `purge_preview_days`) matches the existing URL-parameter-based feedback pattern in the voucher page handler.

**Alternatives considered**:
- **JavaScript modal confirmation**: Rejected — the admin UI is currently server-rendered HTML with minimal JavaScript. Introducing a modal with AJAX would be a significant UX pattern deviation requiring justification per constitution principle III.
- **Single endpoint with GET/POST distinction**: Rejected — mixing GET (for preview) and POST (for execution) on the same endpoint is less clear than two distinct POST endpoints.
- **Separate confirmation page**: Rejected — overly complex for a simple count display. Query-parameter-based feedback on the existing page is sufficient and consistent.

---

### R6: How should concurrent purge operations be handled?

**Decision**: Use SQL DELETE with a WHERE clause that includes the status and age conditions. If a voucher was already deleted by a concurrent operation, the DELETE simply affects zero rows — no error occurs.

**Rationale**:
- SQLite serializes writes, so true concurrent modification is not possible within the same database. However, the spec requires graceful handling (FR-014), and this approach is naturally idempotent.
- The existing `VoucherRepository.delete()` method already uses predicate-based deletion (WHERE clause with conditions) which handles race conditions safely.
- No need for explicit locking, row versioning, or conditional checks before delete.

**Alternatives considered**:
- **SELECT FOR UPDATE + DELETE**: Rejected — SQLite does not support `SELECT FOR UPDATE`. Also unnecessary since SQLite writes are serialized.
- **Application-level mutex/lock**: Rejected — adds complexity with no benefit in a single-instance SQLite deployment.

---

### R7: How should batch efficiency be handled for large purge operations?

**Decision**: Use single SQL statements for both count and delete operations:
- `SELECT COUNT(*) FROM voucher WHERE status IN ('expired', 'revoked') AND status_changed_utc < :cutoff`
- `UPDATE accessgrant SET voucher_code = NULL WHERE voucher_code IN (SELECT code FROM voucher WHERE ...)`
- `DELETE FROM voucher WHERE status IN ('expired', 'revoked') AND status_changed_utc < :cutoff`

**Rationale**:
- Single SQL statements are the most efficient approach for batch operations on SQLite. The database handles the set operation internally without Python-side iteration.
- SC-003 requires completion within 10 seconds for 10,000 vouchers. Single-statement SQL DELETE is well within this limit for SQLite.
- The existing `AuditCleanupService.cleanup_expired_logs()` uses the same pattern (single DELETE with WHERE clause).

**Alternatives considered**:
- **Chunked deletion (batches of 500)**: Considered but deferred — for 10,000 records on SQLite, a single DELETE is fast enough. Chunking adds complexity and is only needed if lock contention becomes an issue, which is unlikely in a single-instance deployment.
- **Soft delete (mark as purged)**: Rejected — the spec says "permanently deleted." Soft delete would not solve the database growth problem.

---

### R8: What audit action names and metadata should be used?

**Decision**: Use the following audit trail format:

| Operation | Actor | Action | Target Type | Meta |
|-----------|-------|--------|-------------|------|
| Auto-purge | `"system"` | `"voucher.auto_purge"` | `"voucher"` | `{"purged_count": N, "retention_days": 30, "cutoff_utc": "..."}` |
| Manual purge | admin username | `"voucher.manual_purge"` | `"voucher"` | `{"purged_count": N, "min_age_days": N, "cutoff_utc": "..."}` |

**Rationale**:
- Follows the existing naming convention: `<entity>.<operation>` (e.g., `voucher.create`, `voucher.revoke`, `event.cleanup`).
- Distinguishing `auto_purge` from `manual_purge` in the action name makes audit log filtering easy.
- Including both the input parameter (`retention_days` or `min_age_days`) and the computed `cutoff_utc` in metadata ensures full traceability.
- Using `actor="system"` for auto-purge follows the pattern in `CleanupService`.

**Alternatives considered**:
- **Single action `"voucher.purge"` with `trigger` in meta**: Considered — but separate action names are clearer for filtering and reporting.
- **Logging each purged voucher individually**: Rejected — would create thousands of audit entries for a single bulk operation. A single summary entry with count is appropriate and matches the `event.cleanup` pattern.
