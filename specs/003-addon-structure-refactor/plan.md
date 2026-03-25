SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Addon Structure Refactor

**Branch**: `003-addon-structure-refactor` | **Date**: 2025-07-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-addon-structure-refactor/spec.md`

## Summary

Restructure the captive-portal HA addon to fully match standard HA addon patterns
as demonstrated by the reference implementation (rentalsync-bridge). The source
code has already been relocated into `addon/src/`; this plan addresses the
remaining structural gaps:

1. Convert `addon/config.json` to `addon/config.yaml` (FR-008)
2. Switch build backend from setuptools to hatchling (FR-015)
3. Adopt the `uv sync --frozen` Dockerfile pattern for reproducible builds (FR-006)
4. Generate `addon/uv.lock` for frozen container builds (FR-020)
5. Use Python-specific HA base images instead of generic ones
6. Update the s6-overlay run script for the new venv path
7. Clean up stale root `src/` directory

No application logic, data models, or test assertions are modified.

## Technical Context

**Language/Version**: Python 3.12+ (runtime: Python 3.13 from HA base image)
**Primary Dependencies**: FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, Argon2-cffi, HTTPX, passlib
**Storage**: SQLite via SQLModel (unchanged by this feature)
**Testing**: pytest (441+ tests: unit, integration, contract, performance)
**Target Platform**: Home Assistant Supervisor (Alpine Linux containers, amd64/aarch64)
**Project Type**: Home Assistant Add-on (web service with admin panel)
**Performance Goals**: 800ms p95 voucher redemption, 1500ms p95 admin listing (per constitution)
**Constraints**: All source within `addon/` build context; s6-overlay process supervision; no files outside build context referenced by Dockerfile
**Scale/Scope**: Single addon, ~50 source files, 441+ tests, 2 architectures

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Phase 0 Check

| # | Principle | Status | Notes |
|---|---|---|---|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | No application code changes; config files get SPDX headers; linting unaffected |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | This is a structural refactor — no new application behavior to TDD. Verification is that all 441+ existing tests pass unchanged (SC-002). New integration tests for build/startup already exist in `tests/integration/test_addon_build_run.py` and `test_addon_startup_wiring.py`. |
| III | User Experience Consistency | ✅ PASS | No user-facing changes; API contracts, portal UI, and admin interface are untouched |
| IV | Performance Requirements | ✅ PASS | No runtime behavior changes; performance baselines unaffected |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | All new files will have SPDX headers (FR-021); commits will be atomic and signed off |
| VI | Phased Development | ✅ PASS | Implementation phases defined below with clear checkpoints |

### Constitution Constraint Check

| Constraint | Status | Notes |
|---|---|---|
| Language & Runtime | ✅ | Python 3.12+ with type annotations enforced by mypy |
| Dependency Management | ✅ | uv with locked dependencies; addon/uv.lock created |
| License Compliance | ✅ | SPDX headers on all new files; REUSE.toml updated as needed |
| Security | ✅ | No credential changes; secrets injected via HA Supervisor config |
| HA Compatibility | ✅ | Explicit goal of this refactor — align with HA addon conventions |
| Observability | ✅ | s6 finish script logs exit codes; no logging changes |

**Gate result: PASS** — No violations. Proceed to Phase 0.

### Post-Phase 1 Re-Check

| # | Principle | Status | Notes |
|---|---|---|---|
| I | Code Quality | ✅ PASS | Design adds no application code; only config/build files modified |
| II | TDD | ✅ PASS | No new behavior requiring TDD; existing test_addon_build_run.py covers build validation |
| III | UX Consistency | ✅ PASS | No user-facing changes in design |
| IV | Performance | ✅ PASS | No runtime changes |
| V | Atomic Commits | ✅ PASS | Each file change is an atomic logical unit |
| VI | Phased Development | ✅ PASS | Two implementation phases with clear checkpoints |

**Gate result: PASS** — Design is constitution-compliant.

## Project Structure

### Documentation (this feature)

```text
specs/003-addon-structure-refactor/
├── plan.md                              # This file
├── research.md                          # Phase 0: Research decisions
├── data-model.md                        # Phase 1: File/directory layout model
├── quickstart.md                        # Phase 1: Developer quickstart guide
├── contracts/
│   └── ha-supervisor-contract.md        # Phase 1: HA Supervisor interface contract
└── tasks.md                             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository layout after refactor)

```text
/ (repo root — development context)
├── pyproject.toml                # uv workspace: members = ["addon"], dev deps
├── uv.lock                       # Root lock (dev + workspace)
├── .mypy.ini                     # mypy config (mypy_path = addon/src)
├── repository.yaml               # HA repository metadata
├── tests/                        # Full test suite (unchanged)
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── performance/
│   └── utils/
├── addon/                        # ← Docker build context
│   ├── Dockerfile                # Container build (uv sync --frozen)
│   ├── build.yaml                # Architecture → Python base image mapping
│   ├── config.yaml               # HA addon metadata (YAML format)
│   ├── pyproject.toml            # Package definition (hatchling backend)
│   ├── uv.lock                   # Frozen runtime dependency lock
│   ├── README.md
│   ├── rootfs/                   # s6-overlay filesystem overlay
│   │   └── etc/s6-overlay/s6-rc.d/
│   │       ├── captive-portal/
│   │       │   ├── run           # uvicorn startup (longrun)
│   │       │   ├── finish        # Exit code logger
│   │       │   └── type          # "longrun"
│   │       └── user/contents.d/
│   │           └── captive-portal
│   └── src/
│       └── captive_portal/       # All application source code
│           ├── __init__.py
│           ├── app.py
│           ├── middleware.py
│           ├── api/
│           ├── config/
│           ├── controllers/
│           ├── integrations/
│           ├── models/
│           ├── persistence/
│           ├── security/
│           ├── services/
│           ├── utils/
│           └── web/
│               ├── middleware/
│               ├── templates/
│               └── themes/
├── docs/
└── specs/
```

**Structure Decision**: HA addon workspace pattern. The addon is a self-contained
build context under `addon/`. The root provides the development workspace
(tests, linting, type-checking) via uv workspace membership. The stale root
`src/` directory (empty dirs + `__pycache__` only) is removed.

## Implementation Phases

### Phase 1: Build Configuration Alignment

**Goal**: Align addon build tooling with the reference pattern so that
`docker build addon/` produces a working container with frozen dependencies.

**Changes**:

1. **`addon/pyproject.toml`** — Switch build backend:
   - Replace `[build-system]` from setuptools to hatchling
   - Replace `[tool.setuptools.*]` with `[tool.hatch.build.targets.wheel]`
   - Set `packages = ["src/captive_portal"]`
   - Verify package-data inclusion (templates, themes) works with hatchling

2. **`addon/uv.lock`** — Generate lock file:
   - Run `cd addon && uv lock` to create `addon/uv.lock`
   - Verify it resolves all runtime dependencies from `addon/pyproject.toml`

3. **`addon/build.yaml`** — Update base images:
   - Change `amd64` to `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21`
   - Change `aarch64` to `ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21`

4. **`addon/Dockerfile`** — Adopt reference pattern:
   - Update default `BUILD_FROM` to Python base image
   - Remove `apk add --no-cache python3`
   - Remove explicit venv creation (`uv venv /opt/venv`)
   - Copy `pyproject.toml` + `uv.lock` → `uv sync --frozen --no-dev --no-install-project`
   - Copy `src/` + `README.md` → `uv sync --frozen --no-dev`
   - Set `PATH="/app/.venv/bin:$PATH"` and `PYTHONUNBUFFERED=1`
   - Copy `rootfs /`

5. **`addon/rootfs/.../captive-portal/run`** — Update venv path:
   - Change `"${VIRTUAL_ENV}/bin/python"` to `python` (on PATH via `.venv`)
   - Or use explicit `/app/.venv/bin/python`

**Checkpoint**: `docker build addon/` succeeds; container starts and responds
on port 8080.

### Phase 2: Metadata and Cleanup

**Goal**: Complete the HA addon convention alignment and clean up stale artifacts.

**Changes**:

1. **`addon/config.yaml`** — Create YAML config:
   - Convert `addon/config.json` to YAML format (semantic content preserved exactly)
   - Add SPDX header

2. **`addon/config.json`** — Delete:
   - Remove the old JSON config after YAML replacement is verified

3. **Root `src/` directory** — Clean up:
   - Remove `src/` at repository root (only contains empty dirs + `__pycache__`)

4. **REUSE.toml** — Update annotations:
   - Update or add annotations for any new file patterns (e.g., `addon/config.yaml`)
   - Remove annotations for deleted patterns (e.g., `config.json` if specifically listed)

5. **Root `pyproject.toml`** — Verify workspace:
   - Confirm `uv sync` from root still installs `captive-portal` as editable
   - Run full test suite: all 441+ tests pass
   - Run `ruff check`, `mypy`, `interrogate` — all pass

**Checkpoint**: Full test suite passes; `docker build addon/` succeeds;
REUSE compliance check passes; no stale artifacts remain.

## Complexity Tracking

> No constitution violations to justify. This refactor aligns with all
> constitution principles without exceptions.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | — | — |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hatchling build backend changes package discovery, breaking imports | Low | High | Run full test suite after switch; hatchling's `packages` config is explicit |
| Python 3.13 base image introduces runtime incompatibility | Low | Medium | Project requires ≥3.12; 3.13 is backward-compatible; tests validate |
| `uv sync --frozen` fails due to lock/pyproject drift | Low | Low | Lock file is generated fresh; CI can validate lock freshness |
| Root `src/` removal breaks a tool or IDE configuration | Low | Low | Verify `.mypy.ini`, `pyproject.toml`, and VSCode settings reference `addon/src` |

## Artifact Index

| Artifact | Path | Phase |
|---|---|---|
| Research decisions | [research.md](research.md) | Phase 0 |
| File/directory layout model | [data-model.md](data-model.md) | Phase 1 |
| HA Supervisor contract | [contracts/ha-supervisor-contract.md](contracts/ha-supervisor-contract.md) | Phase 1 |
| Developer quickstart | [quickstart.md](quickstart.md) | Phase 1 |
| Task list | [tasks.md](tasks.md) | Phase 2 (pending) |
