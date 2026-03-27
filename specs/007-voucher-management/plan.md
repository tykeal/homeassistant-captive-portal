SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Voucher Management

**Branch**: `007-voucher-management` | **Date**: 2025-07-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-voucher-management/spec.md`

## Summary

Add voucher lifecycle management — revoke, delete, and bulk operations — to the existing admin vouchers page. New POST endpoints on `vouchers_ui.py` follow the established Post/Redirect/Get pattern from the grants page. A `VoucherService.revoke()` method (modelled on `GrantService.revoke()`) sets the voucher status to REVOKED after validating expiry eligibility. A `VoucherService.delete()` method enforces the "never redeemed" invariant before hard-deleting the record. The `VoucherRepository` gains a `delete()` method. Bulk operations reuse the same service methods in a loop, collecting per-voucher outcomes into a summary message. The voucher list template adds per-row action forms (revoke/delete buttons) and a checkbox-based selection UI with bulk action controls.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy, full type annotations)
**Primary Dependencies**: FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), python-multipart
**Storage**: SQLite via SQLModel ORM (existing `persistence/database.py` engine)
**Testing**: pytest + pytest-asyncio, TestClient (sync), httpx AsyncClient (perf), pytest-cov
**Target Platform**: Linux (Home Assistant Supervisor add-on, Alpine Docker, s6-overlay)
**Project Type**: Web service / Home Assistant add-on with server-rendered admin UI
**Performance Goals**: Single revoke/delete ≤ 3 s (SC-001/002); bulk revoke of 20 vouchers ≤ 10 s (SC-003); voucher redemption ≤ 800 ms p95 (constitution IV)
**Constraints**: No inline JS (CSP `script-src 'self'`); external JS files only; ingress root_path prefix on all URLs; forms must work without JS; hard delete (no soft delete for vouchers)
**Scale/Scope**: 1–5 concurrent admins; ~200 vouchers typical; 4 new POST endpoints (revoke, delete, bulk-revoke, bulk-delete); ~6 modified/new source files; ~4 new test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new files pass ruff, mypy strict, interrogate 100%. SPDX headers required. Functions ≤ CC10. |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | TDD red-green-refactor for all new service methods and route handlers. Unit tests per route; integration tests for full page flows. |
| III | User Experience Consistency | ✅ PASS | New action buttons follow identical pattern to grants page (inline forms, disabled states, status badges). Feedback via query-parameter flash messages. |
| IV | Performance Requirements | ✅ PASS | Single actions within 3 s budget. Bulk operations iterate with per-voucher commits to allow partial success. No blocking event loop calls. |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | One logical change per commit. SPDX + DCO sign-off. Pre-commit hooks enforced. Conventional Commits. |
| VI | Phased Development | ✅ PASS | Plan defines three priority-ordered phases (P1 revoke, P2 delete, P3 bulk) with independently testable increments and CI checkpoints. |

**Gate result: PASS** — No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/007-voucher-management/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── voucher-management-routes.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── api/routes/
│   └── vouchers_ui.py           # MODIFY — add POST revoke, delete, bulk-revoke, bulk-delete endpoints
├── services/
│   └── voucher_service.py       # MODIFY — add revoke() and delete() methods
├── persistence/
│   └── repositories.py          # MODIFY — add VoucherRepository.delete() method
├── web/
│   ├── templates/admin/
│   │   └── vouchers.html        # MODIFY — add action columns, checkboxes, bulk controls, feedback
│   └── themes/default/
│       └── admin.css             # MODIFY — checkbox, bulk-action-bar styles (minor)
└── app.py                       # EXISTING — no changes expected (vouchers_ui router already registered)

tests/
├── unit/
│   ├── routes/
│   │   └── test_vouchers_ui.py            # MODIFY — add revoke, delete, bulk endpoint tests
│   └── services/
│       ├── test_voucher_service_revoke.py # NEW — revoke service method TDD
│       └── test_voucher_service_delete.py # NEW — delete service method TDD
├── integration/
│   ├── test_admin_voucher_revoke.py       # NEW — full-page revoke flow
│   ├── test_admin_voucher_delete.py       # NEW — full-page delete flow
│   └── test_admin_voucher_bulk_ops.py     # NEW — bulk operations integration
└── performance/
    └── test_admin_list_scaling.py         # EXISTING — extend with bulk ops benchmark
```

**Structure Decision**: Single-project monolith following the existing addon/src layout. All changes extend existing modules (`vouchers_ui.py`, `voucher_service.py`, `repositories.py`) or add new test files. No new packages or route modules needed — the voucher management endpoints are scoped to the existing `/admin/vouchers` prefix.

## Complexity Tracking

> No violations to justify — all gates pass.
