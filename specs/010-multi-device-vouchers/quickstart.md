# Quickstart: Multi-Device Vouchers

**Feature Branch**: `010-multi-device-vouchers`
**Date**: 2025-07-15

## Overview

This feature extends the existing voucher system so a single voucher code can authorize multiple devices (e.g., a guest's phone, laptop, and tablet). The voucher gains a `max_devices` field (default 1) that controls how many devices can redeem it. Existing vouchers and workflows are fully backward-compatible.

## Key Files to Modify

| Layer | File | What Changes |
|-------|------|-------------|
| Model | `addon/src/captive_portal/models/voucher.py` | Add `max_devices` field (int, default 1, ≥1) |
| Migration | `addon/src/captive_portal/persistence/database.py` | Add `_migrate_voucher_max_devices()` |
| Repository | `addon/src/captive_portal/persistence/repositories.py` | Add `count_active_by_voucher_code()` and batch variant |
| Service | `addon/src/captive_portal/services/voucher_service.py` | Modify `create()` to accept `max_devices`; modify `redeem()` to check device capacity |
| Admin API | `addon/src/captive_portal/api/routes/vouchers.py` | Add `max_devices` to request/response models |
| Admin UI route | `addon/src/captive_portal/api/routes/vouchers_ui.py` | Add `max_devices` form field; add bulk-create endpoint; compute device counts |
| Admin template | `addon/src/captive_portal/web/templates/admin/vouchers.html` | Add `max_devices` input; update table with device usage column |

## Implementation Phases

### Phase 1: Model & Migration
1. Add `max_devices` field to `Voucher` model with default 1
2. Add `_migrate_voucher_max_devices()` to `database.py`
3. Register migration in `init_db()`

### Phase 2: Repository & Service
1. Add `count_active_by_voucher_code()` to `AccessGrantRepository`
2. Add `count_active_by_voucher_codes()` batch variant
3. Add `VoucherDeviceLimitError` exception class
4. Modify `VoucherService.create()` to accept and persist `max_devices`
5. Modify `VoucherService.redeem()` to check active grant count against `max_devices`
6. Update duplicate-device error message (FR-008)

### Phase 3: API & Admin UI
1. Add `max_devices` to `CreateVoucherRequest` and `VoucherResponse`
2. Add `max_devices` form input to voucher creation form
3. Add bulk-create endpoint with `max_devices` support
4. Update voucher list to display device usage ("N/M devices")
5. Compute active device counts via batch query in `get_vouchers()`

### Phase 4: Integration Tests & Polish
1. Multi-device redemption flow (1st, 2nd, Nth device, limit exceeded)
2. Backward compatibility (existing vouchers, default max_devices=1)
3. Concurrent redemption race condition test
4. Grant revocation frees device slot test
5. Bulk create with max_devices
6. Admin UI device count display verification

## Running Tests

```bash
# All unit tests
uv run pytest tests/unit/ -x -q

# All integration tests
uv run pytest tests/integration/ -x -q

# Specific voucher-related tests
uv run pytest tests/ -k "voucher" -x -q

# Linting and type checks
uv run ruff check addon/src/ tests/
uv run mypy addon/src/ tests/

# Full CI equivalent
uv run pytest tests/ -x -q && uv run ruff check addon/src/ tests/ && uv run mypy addon/src/
```

## Key Design Decisions

1. **No new voucher status**: Device capacity enforced by counting active grants at redemption time, not by a "FULLY_REDEEMED" status. This keeps grant revocation → slot freeing simple.
2. **Query-based counting**: Active grant counts are queried, not cached as a counter on the Voucher. This ensures accuracy even if grants are revoked asynchronously.
3. **SQLite concurrency**: The single-writer model inherently serializes concurrent redemptions. No additional locking mechanism needed.
4. **Migration pattern**: Follows existing `ALTER TABLE ... ADD COLUMN ... DEFAULT` pattern. No Alembic or external migration tooling.
5. **Backward compatibility**: `max_devices` defaults to 1 everywhere — API, model, migration. Zero breaking changes.

## Dependencies

No new dependencies. The feature uses only existing libraries (SQLModel, FastAPI, Jinja2).
