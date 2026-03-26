SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Admin UI Pages

**Branch**: `005-admin-ui-pages` | **Date**: 2025-07-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-admin-ui-pages/spec.md`

## Summary

Build three admin UI pages — Dashboard, Grants, Vouchers — and wire up proper Logout, completing the admin interface. All pages use server-side rendered Jinja2 templates with HTML form POST actions (CSRF-protected) as the primary interaction mechanism, with optional progressive-enhancement JavaScript. Templates follow the established nav/layout pattern from the existing Settings and Integrations pages. A new `/admin/logout` HTML route performs logout by deleting the current session from `SessionStore`, clearing the auth cookie, and issuing a browser-friendly redirect, without calling the `/api/admin/auth/logout` API. Cache-control headers are added to all admin responses to prevent post-logout back-button content leakage.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy, full type annotations)
**Primary Dependencies**: FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), python-multipart
**Storage**: SQLite via SQLModel ORM (existing `persistence/database.py` engine)
**Testing**: pytest + pytest-asyncio, TestClient (sync), httpx AsyncClient (perf), pytest-cov
**Target Platform**: Linux (Home Assistant Supervisor add-on, Alpine Docker, s6-overlay)
**Project Type**: Web service / Home Assistant add-on with server-rendered admin UI
**Performance Goals**: Admin grant listing (500 grants) ≤ 1500 ms p95; voucher creation ≤ 800 ms p95
**Constraints**: No inline JS (CSP `script-src 'self'`); all external JS files; ingress root_path prefix on all URLs; forms must work without JS
**Scale/Scope**: 1–5 concurrent admins; 4 new pages; ~10 new source files; ~500 grants / ~200 vouchers typical

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new files will pass ruff, mypy strict, interrogate 100%. SPDX headers required. Functions ≤ CC10. |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | TDD red-green-refactor for all route handlers and service methods. Unit tests for each route; integration tests for full page flows. |
| III | User Experience Consistency | ✅ PASS | New pages reuse exact nav bar, layout, CSS classes from existing Settings/Integrations. No deviations. |
| IV | Performance Requirements | ✅ PASS | Grant listing ≤ 1500 ms p95 (existing baseline). Voucher creation ≤ 800 ms p95. No blocking event loop calls. |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | One logical change per commit. SPDX + DCO sign-off. Pre-commit hooks enforced. Conventional Commits. |
| VI | Phased Development | ✅ PASS | Plan defines clear phases with independently testable increments and CI checkpoints. |

**Gate result: PASS** — No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/005-admin-ui-pages/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── admin-html-routes.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── api/routes/
│   ├── dashboard_ui.py          # NEW — GET /admin/dashboard
│   ├── grants_ui.py             # NEW — GET /admin/grants, POST extend/revoke
│   ├── vouchers_ui.py           # NEW — GET /admin/vouchers, POST create
│   ├── admin_logout_ui.py       # NEW — POST /admin/logout (HTML redirect wrapper)
│   ├── admin_auth.py            # EXISTING — /api/admin/auth/* (no changes expected)
│   ├── grants.py                # EXISTING — /api/grants/* (no changes expected)
│   └── vouchers.py              # EXISTING — /api/vouchers (create only; list query added to UI route directly)
├── web/
│   ├── templates/admin/
│   │   ├── dashboard.html       # EXISTING — update: empty-state handling, activity feed timestamp field
│   │   ├── grants_enhanced.html # EXISTING — update: feedback messages, error/empty states, expired-grant disable
│   │   └── vouchers.html        # NEW — voucher list + create form + prominent code display
│   └── themes/default/
│       ├── admin.css             # EXISTING — minor additions: alert styles, voucher-code-display, empty-state
│       └── admin-grants.js       # NEW (optional) — progressive enhancement for grants actions
├── web/middleware/
│   └── security_headers.py      # EXISTING — add cache-control for /admin/* paths
├── services/
│   └── dashboard_service.py     # NEW — aggregate stats + recent activity queries
└── app.py                       # EXISTING — register new UI route modules

tests/
├── unit/
│   ├── routes/
│   │   ├── test_dashboard_ui.py      # NEW
│   │   ├── test_grants_ui.py         # NEW
│   │   ├── test_vouchers_ui.py       # NEW
│   │   └── test_admin_logout_ui.py   # NEW
│   └── services/
│       └── test_dashboard_service.py # NEW
├── integration/
│   ├── test_admin_dashboard_page.py  # NEW
│   ├── test_admin_grants_page.py     # NEW
│   ├── test_admin_vouchers_page.py   # NEW
│   ├── test_admin_logout_flow.py     # NEW (extends existing test_admin_auth_login_logout.py)
│   └── test_admin_cache_headers.py   # NEW
└── performance/
    └── test_admin_list_scaling.py    # EXISTING — extend with voucher list benchmark
```

**Structure Decision**: Single-project monolith following the existing addon/src layout. All new routes live under `api/routes/` as `*_ui.py` modules (consistent with existing `portal_settings_ui.py`, `integrations_ui.py`, `admin_login_ui.py` patterns). Templates in `web/templates/admin/`. No new packages needed.

## Complexity Tracking

> No violations to justify — all gates pass.
