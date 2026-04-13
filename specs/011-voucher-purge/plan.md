# Implementation Plan: Voucher Auto-Purge and Admin Purge

**Branch**: `011-voucher-purge` | **Date**: 2025-07-22 | **Spec**: `specs/011-voucher-purge/spec.md`
**Input**: Feature specification from `/specs/011-voucher-purge/spec.md`

## Summary

Implement automatic and manual purging of expired/revoked vouchers to prevent unbounded database growth. The feature adds a `status_changed_utc` timestamp field to the voucher model (with migration backfill for existing records), a background auto-purge that runs lazily on admin page load (30-day retention), and an admin UI form for on-demand purge with a configurable age threshold (N days, where N=0 means all terminal vouchers). Associated access grants have their voucher reference nullified on purge; audit logs are preserved unchanged. All purge operations are recorded in the audit trail.

## Technical Context

**Language/Version**: Python 3.12+ with strict mypy type checking
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy, Pydantic, Jinja2, Uvicorn, httpx
**Storage**: SQLite (via SQLModel/SQLAlchemy); lightweight schema migrations in `database.py`
**Testing**: pytest + pytest-asyncio + pytest-cov; ruff linting; mypy strict; interrogate 100% docstring coverage
**Target Platform**: Linux (Home Assistant Supervisor add-on container)
**Project Type**: Web service (FastAPI) packaged as a Home Assistant add-on
**Performance Goals**: Auto-purge ≤10s for up to 10,000 terminal vouchers (SC-003); manual purge workflow ≤30s end-to-end (SC-002)
**Constraints**: Must not block FastAPI event loop; SQLite single-writer constraint requires efficient batch operations
**Scale/Scope**: Single-instance SQLite database, up to 10,000 expired/revoked vouchers in a typical deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Pre-design | Post-design | Notes |
|-----------|--------|------------|-------------|-------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | ✅ | ✅ | All new code will pass ruff, mypy strict, interrogate 100%. Functions have docstrings, type annotations, and ≤10 cyclomatic complexity. SPDX headers on all new files. New `VoucherPurgeService` keeps methods focused and simple. |
| II. Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | ✅ | ✅ | TDD red-green-refactor for all production code. Unit tests for purge service, repository methods, model changes. Integration tests for admin UI flow and auto-purge-on-page-load. Phase-aligned test plan in quickstart.md. |
| III. User Experience Consistency | ✅ PASS | ✅ | ✅ | Manual purge UI follows existing admin page patterns (form + CSRF + confirmation + Post/Redirect/Get). Two-step preview/confirm flow matches existing bulk operation patterns. Error messages are actionable. |
| IV. Performance Requirements | ✅ PASS | ✅ | ✅ | Purge uses batch SQL DELETE (not row-by-row). Count query precedes delete for confirmation. No event loop blocking. Batch grant nullification via single UPDATE. |
| V. Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | ✅ | ✅ | One logical change per commit. DCO sign-off, SPDX headers, Conventional Commits with capitalized types. Pre-commit hooks not bypassed. |
| VI. Phased Development | ✅ PASS | ✅ | ✅ | Three phases: (1) Model + migration + timestamp tracking, (2) Auto-purge service + lazy trigger, (3) Admin manual purge UI. Each phase independently testable with clear boundaries documented in quickstart.md. |

**Gate result: PASS** — No violations at either check. Design is constitution-compliant.

## Project Structure

### Documentation (this feature)

```text
specs/011-voucher-purge/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal-only project; minimal)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── models/
│   └── voucher.py               # Add status_changed_utc field
├── persistence/
│   ├── database.py              # Add _migrate_voucher_status_changed_utc()
│   └── repositories.py          # Add purge query methods to VoucherRepository
├── services/
│   ├── voucher_service.py       # Set status_changed_utc on transitions; add purge methods
│   └── voucher_purge_service.py # New: auto-purge + manual purge orchestration
├── api/routes/
│   └── vouchers_ui.py           # Add purge form handling + lazy auto-purge trigger
└── web/templates/admin/
    └── vouchers.html            # Add purge UI section

tests/
├── unit/
│   ├── models/test_voucher_model.py          # status_changed_utc tests
│   ├── services/test_voucher_purge_service.py # New: purge service unit tests
│   └── services/test_voucher_service_expire.py # Update: status_changed_utc on expire
└── integration/
    ├── test_admin_voucher_purge.py            # New: manual purge UI integration tests
    └── test_admin_vouchers_page.py            # Update: auto-purge on page load
```

**Structure Decision**: Follows the existing single-project structure rooted at `addon/src/captive_portal/`. The purge orchestration logic is in a new `VoucherPurgeService` to keep `VoucherService` focused on individual voucher lifecycle operations, following the same separation pattern as `CleanupService` for events.

## Complexity Tracking

No constitution violations — this section is intentionally empty.
