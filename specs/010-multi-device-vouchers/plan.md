# Implementation Plan: Multi-Device Vouchers

**Branch**: `010-multi-device-vouchers` | **Date**: 2025-07-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-multi-device-vouchers/spec.md`

## Summary

Allow vouchers to authorize N number of devices (defaulting to 1). Currently a voucher can only be claimed by a single device. This feature adds a `max_devices` field to the `Voucher` model so a single voucher code can be redeemed by multiple devices (e.g., a guest's phone, laptop, and tablet). The implementation extends the existing Voucher model with a new column, modifies the redemption logic to count active (non-revoked) grants instead of treating any redemption as terminal, updates the admin UI to display device usage ("2/5 devices"), and adds an atomic concurrency guard to prevent exceeding the device limit under race conditions.

## Technical Context

**Language/Version**: Python 3.12+ with strict mypy type checking
**Primary Dependencies**: FastAPI, SQLModel (SQLAlchemy), Pydantic, Jinja2, httpx, uvicorn
**Storage**: SQLite via SQLModel/SQLAlchemy ORM (lightweight migration pattern for schema changes)
**Testing**: pytest, pytest-asyncio, pytest-cov; ruff + mypy + interrogate for static analysis
**Target Platform**: Linux (Home Assistant Supervisor add-on, Docker container)
**Project Type**: Web service (FastAPI) + Admin UI (server-side Jinja2 templates) + Guest captive portal
**Performance Goals**: Voucher redemption <800ms p95 at 50 concurrent requests (per constitution)
**Constraints**: Must not block FastAPI event loop; SQLite single-writer concurrency model; cyclomatic complexity ≤10 per function
**Scale/Scope**: Small-to-medium deployment (single property: hotel, Airbnb); typically <500 active vouchers, <50 concurrent guests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will include docstrings, type annotations, SPDX headers. Ruff C901 ≤10 enforced. |
| II. Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | Red-green-refactor for all new logic. Unit tests for model/service changes, integration tests for redemption flow. |
| III. User Experience Consistency | ✅ PASS | Admin UI extends existing voucher list table with usage column. Guest portal error messages remain actionable. API contracts documented. |
| IV. Performance Requirements | ✅ PASS | Redemption uses existing single-query-per-voucher pattern + atomic grant count check. No new external calls. SQLite write lock is the concurrency bottleneck (addressed via retry). |
| V. Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | One logical change per commit. SPDX headers. DCO sign-off. Conventional Commits with capitalized types. |
| VI. Phased Development | ✅ PASS | Plan defines clear phases with independently testable increments. |

**Pre-Phase 0 Gate**: ✅ ALL PASSED

## Project Structure

### Documentation (this feature)

```text
specs/010-multi-device-vouchers/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contract updates)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── models/
│   └── voucher.py              # Add max_devices field
├── persistence/
│   ├── database.py             # Add migration for max_devices column
│   └── repositories.py         # Add count_active_grants_for_voucher()
├── services/
│   └── voucher_service.py      # Modify redeem() logic, add create() max_devices param
├── api/routes/
│   ├── vouchers.py             # Add max_devices to CreateVoucherRequest/Response
│   └── vouchers_ui.py          # Add max_devices to create form, usage display
├── web/templates/admin/
│   └── vouchers.html           # Add max_devices input + usage column

tests/
├── unit/
│   ├── models/                 # Voucher model validation tests
│   ├── services/               # VoucherService redeem/create tests
│   └── persistence/            # Repository query tests
└── integration/
    ├── test_guest_authorization_flow_voucher.py  # Multi-device redemption E2E
    └── test_admin_voucher_bulk_ops.py            # Bulk create with max_devices
```

**Structure Decision**: The existing monolithic add-on structure under `addon/src/captive_portal/` is used. No new packages or structural changes needed — this feature modifies existing files in models, services, persistence, API routes, and templates layers.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.
