SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Omada Controller Integration Wiring

**Branch**: `008-omada-controller-wiring` | **Date**: 2025-07-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-omada-controller-wiring/spec.md`

## Summary

Wire the existing, fully-implemented `OmadaClient` and `OmadaAdapter` into the captive portal application lifecycle. This feature closes 9 integration gaps: addon config schema, application settings model, s6 service scripts, admin app lifespan, guest app lifespan, guest authorization flow, admin grant revocation flow, documentation port fixes (8080→8099), and contract tests. No new controller client logic is written — this is purely about connecting existing components to the running application.

**Technical approach**: Extend `AppSettings` with 6 Omada fields following the established three-tier precedence pattern. Construct `OmadaClient` + `OmadaAdapter` during app lifespan startup (no network I/O), store on `app.state`, and inject via FastAPI dependency injection into authorization and revocation routes. Authentication deferred to first controller operation (lazy init). Both admin (8080) and guest (8099) apps get independent instances.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI, httpx, SQLModel, Pydantic, uvicorn, passlib, argon2-cffi
**Storage**: SQLite via SQLModel (ORM), path: `/data/captive_portal.db`
**Testing**: pytest + pytest-asyncio, ruff (linting), mypy (strict), interrogate (docstrings)
**Target Platform**: Linux (Home Assistant OS / Supervisor addon), amd64 + aarch64
**Project Type**: Web service (dual-port FastAPI addon for Home Assistant)
**Performance Goals**: Voucher redemption < 800ms p95 @ 50 concurrent; Controller propagation < 25s p95
**Constraints**: No blocking calls on event loop; no startup network I/O to controller; password never logged
**Scale/Scope**: ~4,600 LOC Python, 20 API route modules, 12 services, dual-port architecture

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will have docstrings, type annotations, pass ruff/mypy/interrogate. No function > CC 10. SPDX headers on all new files. |
| II. Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | Contract tests already exist as TDD red stubs. Unit tests for settings, lifespan, and flow wiring will follow red-green-refactor. |
| III. User Experience Consistency | ✅ PASS | Guest error messages on controller failure will be actionable (FR-012). API contracts documented. Sensible defaults (no Omada config → graceful degradation). |
| IV. Performance Requirements | ✅ PASS | Lazy init avoids startup latency. Controller calls are async (httpx). No blocking on event loop. |
| V. Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | Each gap = logical commit. SPDX headers, DCO sign-off, Conventional Commits, pre-commit hooks enforced. |
| VI. Phased Development | ✅ PASS | 4 phases defined: config/settings → lifecycle → flows → tests/docs. Each independently testable. |
| Security: Secrets | ✅ PASS | `omada_password` excluded from `log_effective()`. FR-005 explicitly requires password never logged. |
| Observability | ✅ PASS | Structured logging for controller init, auth success/failure, revocation. Audit log entries for all operations. |

**Pre-Phase 0 Gate**: ✅ ALL PASS — no violations, no complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/008-omada-controller-wiring/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── controller-adapter.md
└── tasks.md             # Phase 2 output (NOT created by plan)
```

### Source Code (repository root)

```text
addon/
├── config.yaml                          # +6 Omada schema fields (FR-001)
├── src/captive_portal/
│   ├── config/
│   │   └── settings.py                  # +6 Omada fields in AppSettings (FR-002)
│   ├── controllers/
│   │   └── tp_omada/
│   │       ├── base_client.py           # EXISTING — no changes
│   │       ├── adapter.py               # EXISTING — no changes
│   │       └── __init__.py              # EXISTING — no changes
│   ├── app.py                           # +lifespan: construct client/adapter (FR-006/007)
│   ├── guest_app.py                     # +lifespan: construct client/adapter (FR-006/007)
│   └── api/routes/
│       ├── guest_portal.py              # +controller authorize call (FR-010/011/012/013)
│       └── grants.py                    # +controller revoke call (FR-014/015/016/017/018)
├── rootfs/etc/s6-overlay/s6-rc.d/
│   ├── captive-portal/run               # +export CP_OMADA_* env vars (FR-003)
│   └── captive-portal-guest/run         # +export CP_OMADA_* env vars (FR-003)
docs/
│   └── tp_omada_setup.md                # Fix port 8080→8099 references (FR-019)
tests/
│   └── contract/tp_omada/
│       ├── test_authorize_flow.py       # Unskip + implement (FR-020/021/022)
│       ├── test_revoke_flow.py          # Unskip + implement (FR-020/021/022)
│       └── test_adapter_error_retry.py  # Unskip + implement (FR-020/021/022)
```

**Structure Decision**: Existing single-project addon structure. All changes integrate into established modules — no new packages or structural reorganization needed.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Post-Phase 1 Constitution Re-Check

| Principle | Status | Design Impact |
|-----------|--------|---------------|
| I. Code Quality | ✅ PASS | Data model uses existing Pydantic/SQLModel patterns. No new complex functions needed — wiring code is straightforward if/else branching. |
| II. TDD | ✅ PASS | 16 contract test stubs exist. Settings tests will be added. Lifespan tests will follow existing FastAPI app startup/shutdown test patterns already used in the test suite. |
| III. UX Consistency | ✅ PASS | Controller failure surfaces as actionable guest error message. Admin sees partial-failure notification on revoke. Graceful degradation when unconfigured. |
| IV. Performance | ✅ PASS | No new blocking calls. Adapter uses async httpx. Lazy init prevents startup delay. Retry backoff is bounded at 7s max (3 sleeps: 1s + 2s + 4s). |
| V. Atomic Commits | ✅ PASS | 9 gaps map cleanly to atomic commits: config, settings, s6, admin-lifespan, guest-lifespan, auth-flow, revoke-flow, tests, docs. |
| VI. Phased Development | ✅ PASS | Phase boundaries at: config/settings → lifecycle → flows → tests/docs. Each phase produces independently testable output. |
| Security | ✅ PASS | Password field documented as never-logged in data-model.md. Contract documents adapter exceptions — no credential leakage in error messages. |

**Post-Design Gate**: ✅ ALL PASS — design is constitution-compliant. Ready for Phase 2 task generation.
