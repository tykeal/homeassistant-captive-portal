SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Wire Real Application into Addon Container

**Branch**: `002-addon-app-wiring` | **Date**: 2026-03-25 | **Spec**: ./spec.md
**Input**: Feature specification from `/specs/002-addon-app-wiring/spec.md`

## Summary

Wire the existing captive portal application (FastAPI + SQLModel + 12 routers + 8
models + 10 services) into the Home Assistant addon container, replacing the
current placeholder startup. This requires: (1) a new `AppSettings` configuration
layer merging addon options, environment variables, and defaults with proper
precedence; (2) a production Dockerfile that installs the full `captive_portal`
package; (3) a startup script that reads `/data/options.json`, initializes the
database, and launches uvicorn; (4) template/static path resolution that works
inside the installed package; and (5) graceful shutdown with clean database
connection closure.

## Technical Context

**Language/Version**: Python 3.13+ (per `pyproject.toml` `requires-python = ">=3.13"`)
**Primary Dependencies**: FastAPI, uvicorn\[standard\], SQLModel, Jinja2, pydantic, argon2-cffi, httpx, passlib, python-multipart, email-validator
**Storage**: SQLite via SQLModel/SQLAlchemy at `/data/captive_portal.db` (persistent HA addon volume)
**Testing**: pytest + pytest-asyncio + pytest-cov; unit / integration / contract / performance categories
**Target Platform**: Home Assistant addon container (Alpine Linux base, amd64 + aarch64)
**Project Type**: Web service packaged as a Home Assistant addon
**Performance Goals**: Application ready within 30 seconds of container start (SC-001); voucher redemption ≤800 ms p95 at 50 concurrent (constitution); clean shutdown ≤10 seconds (SC-008)
**Constraints**: Single-process uvicorn (no Gunicorn workers); database on persistent `/data/` volume; no internet access at runtime for dependency installation
**Scale/Scope**: Single Home Assistant instance; <50 concurrent guests; <5 admin users; 63 source files, 78 test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will pass ruff, mypy, interrogate. New files get SPDX headers per user instruction (2026 Andrew Grimberg, Apache-2.0). Existing files retain 2025 headers. |
| II. TDD (NON-NEGOTIABLE) | ✅ PASS | Existing `test_settings_load.py` placeholders will be activated first (red), then AppSettings implemented (green). New integration tests for addon startup precede run.sh changes. |
| III. UX Consistency | ✅ PASS | No UI changes. Configuration exposed via standard HA addon config panel. Existing routes and templates unchanged (FR-014). |
| IV. Performance Requirements | ✅ PASS | No new performance-sensitive paths. Startup ≤30 s validated via integration test. Existing benchmarks unaffected. |
| V. Atomic Commits (NON-NEGOTIABLE) | ✅ PASS | Task breakdown enforces one logical change per commit. SPDX headers on all new files. DCO sign-off required. |
| VI. Phased Development | ✅ PASS | Three implementation phases with checkpoint gates (see Phase Breakdown below). |
| Additional: Security | ✅ PASS | No secrets committed. Addon options read from Supervisor-written file. Password hashing unchanged (Argon2). |
| Additional: HA Compatibility | ✅ PASS | Addon follows HA addon conventions: `config.json` schema, `/data/options.json` input, `BUILD_FROM` arg for multi-arch. |
| Additional: License Compliance | ✅ PASS | REUSE.toml covers generated files. New source files get explicit SPDX headers. |

**Gate result: PASS — proceed to Phase 0.**

## Project Structure

### Documentation (this feature)

```text
specs/002-addon-app-wiring/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── addon-options-schema.json
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/captive_portal/
├── app.py               # MODIFY: accept AppSettings, wire DB init + shutdown
├── __init__.py          # EXISTING: re-exports create_app
├── config/              # NEW: application settings module
│   ├── __init__.py
│   └── settings.py      # AppSettings pydantic model + addon options loader
├── persistence/
│   └── database.py      # EXISTING: create_db_engine(), init_db(), get_session()
├── api/routes/
│   ├── guest_portal.py  # MODIFY: fix template path resolution
│   ├── portal_settings_ui.py  # MODIFY: fix template path resolution
│   └── integrations_ui.py     # MODIFY: fix template path resolution
├── web/
│   ├── templates/       # EXISTING: 12 Jinja2 HTML templates (unchanged)
│   └── themes/          # EXISTING: CSS themes (unchanged)
├── security/
│   └── session_middleware.py   # EXISTING: SessionConfig (consumed by AppSettings)
└── [all other existing modules unchanged]

addon/
├── config.json          # MODIFY: add schema with log_level, session options
├── Dockerfile           # MODIFY: install full captive_portal package
└── rootfs/usr/bin/
    └── run.sh           # MODIFY: replace placeholder with real startup

tests/
├── unit/config/
│   ├── test_settings_load.py           # MODIFY: activate skipped tests + add new tests
│   └── test_addon_options_loader.py    # NEW: addon options.json parsing tests
├── integration/
│   └── test_addon_startup_wiring.py  # NEW: app factory with settings integration test
└── [all existing tests unchanged — FR-015]
```

**Structure Decision**: Existing single-project layout. New code limited to
`src/captive_portal/config/` (settings module) and modifications to `addon/`
(Dockerfile, config.json, run.sh) and route modules (template path fix). No
new top-level directories.

## Phase Breakdown & TDD Sequencing

### Phase 1: Configuration Layer

**Goal**: Create `AppSettings` that merges addon options → env vars → defaults.

**Deliverables**: `src/captive_portal/config/settings.py`, activated
`test_settings_load.py`, new `test_addon_options_loader.py`.

**Tests first**:
- Activate existing skipped tests in `test_settings_load.py` (defaults, env override, validation, secret redaction, DB path).
- New `test_addon_options_loader.py`: valid options.json parsing, missing file fallback, invalid values ignored with warning, partial options merge.
- New `test_settings_precedence.py`: addon option > env var > default; invalid addon value falls through to env var; invalid addon value + no env var falls through to default.

**Constitution Gate**: SPDX headers on new files. Tests fail (red) before implementation.

### Phase 2: Container Wiring

**Goal**: Dockerfile installs full package; run.sh starts real app with settings.

**Deliverables**: Updated `addon/Dockerfile`, updated `addon/rootfs/usr/bin/run.sh`,
updated `addon/config.json` schema, template path fixes in route modules.

**Tests first**:
- New `test_addon_startup_wiring.py`: app factory accepts settings, DB initialized, all routes respond.
- New `test_template_resolution.py`: templates load via package-relative paths.
- Existing `test_addon_build_run.py` updated to validate real app (not placeholder).

**Constitution Gate**: All existing tests pass (FR-015). SPDX headers on new/modified files.

### Phase 3: Shutdown & Hardening

**Goal**: Graceful shutdown, startup logging, edge case handling.

**Deliverables**: Shutdown hook in app lifecycle, startup config logging, error
handling for unwritable `/data/`, missing dependencies.

**Tests first**:
- New `test_graceful_shutdown.py`: DB connections closed on app shutdown event.
- New `test_startup_logging.py`: effective config logged at startup (no secrets).
- New `test_data_dir_errors.py`: clear error on unwritable data directory.

**Constitution Gate**: All CI tests green. No skipped tests remain for this feature.

## Complexity Tracking

No constitution violations. All changes follow existing patterns:
- `AppSettings` uses pydantic `BaseModel` (consistent with `SessionConfig`, `CSRFConfig`).
- Template path fix uses `pathlib.Path(__file__).parent` (standard Python packaging pattern).
- Dockerfile follows existing HA addon conventions.
- No new architectural patterns or abstractions introduced.

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Post-Design Evidence |
|-----------|--------|---------------------|
| I. Code Quality | ✅ PASS | `AppSettings` is a pydantic BaseModel with full type annotations. No complex logic (max cyclomatic complexity ~3 in `load()`). All new files have SPDX headers. |
| II. TDD | ✅ PASS | 5 existing test placeholders activated + 2 new test files designed before implementation. Tests cover defaults, env vars, addon options, precedence, validation, and edge cases. |
| III. UX Consistency | ✅ PASS | HA configuration panel uses standard addon schema conventions. No UI component changes. API contract preserved (FR-014). |
| IV. Performance | ✅ PASS | Settings loaded once at startup (not per-request). Template path resolution computed once at import time. No performance regression paths. |
| V. Atomic Commits | ✅ PASS | Phase breakdown yields ~8-12 atomic commits (test file, settings module, dockerfile, run.sh, config.json, template fixes, shutdown, logging — each independent). |
| VI. Phased Development | ✅ PASS | Three phases with checkpoint gates. Each phase independently testable. |

**Post-design gate result: PASS — ready for task generation.**
