SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Integrations Auto-Detection

**Branch**: `006-integrations-auto-detect` | **Date**: 2025-07-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-integrations-auto-detect/spec.md`

## Summary

Replace the free-text integration ID input on the admin integrations page with an auto-detected pick-list of Rental Control integrations discovered from Home Assistant. A new `HADiscoveryService` queries the HA REST API (`GET /api/states`) to enumerate `calendar.rental_control_*` entities, extracting friendly names, current state, active booking counts, and calendar attributes. The integrations UI route calls the discovery service at page load and passes both discovered and configured integrations to the Jinja2 template. When the HA API is unreachable, returns an error, or times out (10 s), the UI gracefully falls back to the existing manual text entry field with a notification explaining why auto-detection is unavailable. A new JSON endpoint (`GET /api/integrations/discover`) powers a refresh button via progressive-enhancement JavaScript, allowing the admin to re-query without a full page reload. Already-configured integrations are visually marked and prevented from duplicate selection.

## Technical Context

**Language/Version**: Python 3.12+ (strict mypy, full type annotations)
**Primary Dependencies**: FastAPI 0.100+, Jinja2, SQLModel (SQLAlchemy + Pydantic), httpx (async HTTP client for HA REST API), python-multipart
**Storage**: SQLite via SQLModel ORM (existing `persistence/database.py` engine)
**Testing**: pytest + pytest-asyncio, TestClient (sync), httpx AsyncClient, pytest-cov
**Target Platform**: Linux (Home Assistant Supervisor add-on, Alpine Docker, s6-overlay)
**Project Type**: Web service / Home Assistant add-on with server-rendered admin UI
**Performance Goals**: Integration discovery ≤ 5 s under normal conditions (SC-005); fallback presented within 10 s (SC-004)
**Constraints**: No inline JS (CSP `script-src 'self'`); ingress root_path prefix on all URLs; forms must work without JS; HA API token from `SUPERVISOR_TOKEN` env var
**Scale/Scope**: 1–20+ Rental Control integrations; 1–5 concurrent admins; ~6 modified/new source files; ~4 new test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new files will pass ruff, mypy strict, interrogate 100%. SPDX headers required. Functions ≤ CC10. |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | TDD red-green-refactor for discovery service, API endpoint, and UI route. Unit tests mock HA API. Integration tests verify full page flows. Existing skipped contract tests in `tests/contract/ha/test_entity_discovery.py` will be implemented. |
| III | User Experience Consistency | ✅ PASS | Pick-list reuses existing form group/control/button CSS classes. Manual fallback preserves exact current behavior. Nav bar and page layout unchanged. Error notifications follow established alert pattern. |
| IV | Performance Requirements | ✅ PASS | Discovery completes ≤ 5 s (SC-005). 10 s timeout with fallback (SC-004). No blocking event loop — httpx is fully async. |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | One logical change per commit. SPDX + DCO sign-off. Pre-commit hooks enforced. Conventional Commits. |
| VI | Phased Development | ✅ PASS | Plan defines clear phases with independently testable increments and CI checkpoints. |

**Gate result: PASS** — No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/006-integrations-auto-detect/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── discovery-api.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── integrations/
│   ├── ha_client.py                 # EXISTING — add get_all_states() method
│   └── ha_discovery_service.py      # NEW — discover Rental Control integrations from HA
├── api/routes/
│   ├── integrations.py              # EXISTING — add GET /api/integrations/discover endpoint
│   └── integrations_ui.py           # EXISTING — modify to call discovery service, pass results to template
├── web/
│   ├── templates/admin/
│   │   └── integrations.html        # EXISTING — replace free-text input with pick-list + manual fallback
│   └── themes/default/
│       ├── admin.css                # EXISTING — add discovery-related styles (loading, status badges, empty-state)
│       └── admin-integrations.js    # NEW — progressive enhancement: refresh button fetch + dropdown update
└── app.py                           # EXISTING — no changes expected (integrations router already registered)

tests/
├── unit/
│   └── integrations/
│       └── test_ha_discovery_service.py    # NEW — unit tests for discovery service
├── integration/
│   └── test_integrations_auto_detect.py    # NEW — integration tests for page + discovery flow
├── contract/
│   └── ha/
│       └── test_entity_discovery.py        # EXISTING (skipped) — implement contract tests
└── conftest.py                             # EXISTING — add HA API mock fixtures
```

**Structure Decision**: Single-project monolith following the existing addon/src layout. New discovery service in `integrations/` alongside the existing `ha_client.py` and `rental_control_service.py`. Discovery API endpoint added to the existing `integrations.py` router. UI changes are modifications to the existing `integrations_ui.py` route and `integrations.html` template. New JS file for progressive enhancement refresh. No new packages or structural changes needed.

## Complexity Tracking

> No violations to justify — all gates pass.
