# Research: Multi-Device Vouchers

**Feature Branch**: `010-multi-device-vouchers`
**Date**: 2025-07-15

## R1: SQLite Concurrency for Atomic Grant Counting

**Context**: FR-006 requires atomic handling of concurrent redemption attempts to prevent exceeding the max_devices limit. SQLite uses a single-writer model with WAL mode.

**Decision**: Use a predicate-based check within the existing SQLModel session transaction. The redemption flow already runs inside a single `session.commit()` — the grant count check and grant insert happen in the same transaction. SQLite's implicit exclusive write lock during `COMMIT` ensures that two concurrent redemptions cannot both see the same count and both proceed. If contention occurs, SQLAlchemy will raise an `OperationalError` (database is locked) which should be caught and retried.

**Rationale**: The existing codebase already handles concurrency via SQLite's transaction isolation (e.g., the predicate-based delete in `VoucherRepository.delete()`). No new locking mechanism is needed — the single-writer model inherently serializes writes. The application's request volume (small property, <50 concurrent guests) makes contention extremely rare.

**Alternatives considered**:
- **Optimistic locking with version column**: Adds complexity to the model with a version counter. Rejected because SQLite's write serialization already provides the needed guarantee without schema changes.
- **SELECT FOR UPDATE**: Not supported by SQLite. Would require PostgreSQL migration. Rejected as overengineered for the target scale.
- **Application-level asyncio Lock**: Would work for a single-process deployment but breaks if multiple workers are ever configured. Rejected because the database-level guarantee is more robust and already in place.

## R2: Schema Migration Strategy for `max_devices` Column

**Context**: The project uses lightweight in-place migrations via `init_db()` in `database.py`. Existing patterns add columns with `ALTER TABLE` and backfill defaults.

**Decision**: Follow the established migration pattern in `database.py`:
1. Add a `_migrate_voucher_max_devices()` function that checks if `max_devices` column exists.
2. If missing, run `ALTER TABLE voucher ADD COLUMN max_devices INTEGER DEFAULT 1`.
3. The `DEFAULT 1` ensures all existing vouchers are treated as single-device (FR-013 backward compatibility).
4. No data backfill needed — the DEFAULT clause handles it.

**Rationale**: This matches the exact pattern used for `activated_utc`, Omada params, and `allowed_vlans` migrations. Minimal code, no downtime, fully backward compatible.

**Alternatives considered**:
- **Alembic migrations**: A full migration framework. Rejected because the project intentionally uses lightweight ALTER TABLE migrations for simplicity in the HA add-on context (no migration runner infrastructure).
- **Computed default at read time (no column)**: Would count grants per voucher dynamically. Rejected because the spec explicitly calls for a `max_devices` field on the voucher entity, and a persisted column enables simple admin UI display and admin control.

## R3: Grant Counting Strategy (Active vs Total)

**Context**: FR-003 specifies tracking "distinct devices that have redeemed each voucher by counting active (non-revoked) grants." FR-007 says revoked grants don't count.

**Decision**: Count grants with status in `(PENDING, ACTIVE)` for a given `voucher_code`. Do not count `REVOKED`, `EXPIRED`, or `FAILED` grants. This means revoking a grant frees up a slot for a new device.

The count query will be: `SELECT COUNT(*) FROM accessgrant WHERE voucher_code = ? AND status NOT IN ('revoked', 'failed')`.

Note: `EXPIRED` grants are included in the count because expiration is time-based and the voucher itself tracks expiration — an expired grant still represents a device that used the voucher within its window. However, after reconsideration: the spec says "active (non-revoked) grants" and FR-007 specifically says "revoked grants" don't count. Expired and failed grants represent slots that are no longer actively consuming the voucher's capacity. The safest interpretation: only count `PENDING` and `ACTIVE` status grants.

**Rationale**: Aligns with FR-007 (revoked grants free slots) and FR-003 (count "active" grants). Using status-based counting rather than a counter field ensures accuracy even if grants are revoked after the fact.

**Alternatives considered**:
- **Increment/decrement counter on Voucher**: A `devices_used` counter incremented on redeem, decremented on revoke. Rejected because it introduces a consistency risk — the counter could drift from reality if a revoke fails midway. Query-based counting is always accurate.
- **Count all grants regardless of status**: Would mean revoked grants permanently consume slots. Rejected because it contradicts FR-007.

## R4: Voucher Status Transition for Multi-Device

**Context**: Currently, `redeem()` transitions the voucher from `UNUSED` → `ACTIVE` on first redemption. With multi-device vouchers, the voucher stays `ACTIVE` across multiple redemptions.

**Decision**: Keep the existing status transition logic unchanged:
- First redemption: `UNUSED` → `ACTIVE`, sets `activated_utc`
- Subsequent redemptions: Voucher stays `ACTIVE`, `redeemed_count` increments, `last_redeemed_utc` updates
- The voucher never transitions to a "fully redeemed" state based on device count — status remains `ACTIVE` until expired or revoked
- The enforcement of device limits is done at redemption time by counting grants, not by changing voucher status

**Rationale**: This preserves backward compatibility and avoids introducing a new status value. A voucher with `max_devices=1` behaves identically to today: after one redemption it's `ACTIVE`, and any second attempt is rejected by the grant count check (1 active grant ≥ max_devices of 1). The `redeemed_count` field continues to track total redemptions for audit purposes.

**Alternatives considered**:
- **New `FULLY_REDEEMED` status**: Would add a status transition when `active_grants >= max_devices`. Rejected because it creates coupling between grant state and voucher status that can become inconsistent if grants are revoked. The current approach keeps status simple and delegates capacity enforcement to the grant count.

## R5: Duplicate Device Detection for Multi-Device Vouchers

**Context**: FR-008 requires recognizing when a device already authorized under a voucher tries to redeem again. The existing code already checks for duplicate MAC+voucher_code.

**Decision**: Keep the existing duplicate detection logic in `VoucherService.redeem()`. The current check (`find_active_by_mac(mac)` then checking `grant.voucher_code == code`) already prevents the same device from consuming an additional slot. The error message should be updated to be more user-friendly: "Your device is already authorized with this code" instead of the current technical message.

**Rationale**: The existing logic already handles this edge case correctly. No structural change needed — only a message text update.

**Alternatives considered**:
- **Return existing grant instead of error**: Would silently succeed and return the existing grant. Rejected because it could mask issues and doesn't match the spec requirement to "inform the guest."

## R6: Bulk Creation with max_devices

**Context**: FR-010 requires admins to specify `max_devices` when creating vouchers in bulk. The current codebase does not have a bulk create endpoint — bulk operations only exist for revoke and delete.

**Decision**: Add a `max_devices` field to the single `CreateVoucherRequest` and the UI create form. For bulk creation, add a new `/admin/vouchers/bulk-create` endpoint and corresponding form section in the admin UI template. The bulk create form accepts `count`, `duration_minutes`, `max_devices`, `booking_ref`, and `allowed_vlans`. Each voucher in the batch is created via `VoucherService.create()` with the shared `max_devices` value.

**Rationale**: The spec explicitly calls out bulk creation (FR-010, US-2 AS-3). The existing bulk revoke/delete patterns in `vouchers_ui.py` provide a template for the bulk create implementation.

**Alternatives considered**:
- **CSV import for bulk**: Overly complex for the use case. Admins want to create N identical vouchers, not import varying configurations. Rejected.
- **API-only bulk (no UI)**: Would not satisfy the "admin creates through the admin UI" requirement. Rejected.

## R7: Admin UI Usage Display

**Context**: FR-012 requires displaying "2/5 devices" usage status for each voucher in the admin list.

**Decision**: Add a new "Devices" column to the vouchers table in `vouchers.html`. The backend route (`get_vouchers`) will compute the active grant count per voucher using a batch query. For vouchers with `max_devices=1`, the display should be backward-compatible: show "Redeemed" / "Unredeemed" as today, with the device count as a secondary indicator. For `max_devices > 1`, show "N/M devices" format.

The active grant count will be computed via a single query that counts grants grouped by `voucher_code` with status filter, rather than N+1 queries per voucher.

**Rationale**: Batch query avoids N+1 performance issue on the voucher list page (which loads up to 500 vouchers). The display format matches the spec's example ("2/5 devices") from US-3.

**Alternatives considered**:
- **Store count on voucher model (denormalized)**: Would require keeping a counter in sync. Rejected per R3 findings — query-based counting is more reliable.
- **Lazy-load count via JavaScript/AJAX**: Over-engineered for a server-rendered page. Rejected.
