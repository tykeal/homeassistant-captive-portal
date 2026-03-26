SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Dual-Port Networking

**Branch**: `004-dual-port-networking` | **Date**: 2025-07-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-dual-port-networking/spec.md`

## Summary

Add a second network listener to the captive-portal addon so that guest-facing
captive portal traffic (authorization, captive detection, guest API) is served
on a dedicated port (`8099`) directly accessible on the local network, while the
existing ingress listener (`8080`) continues to serve all routes (admin + guest)
behind Home Assistant authentication.  The two listeners run as independent
s6-overlay `longrun` services sharing a single FastAPI application with
route-policy–based filtering.  The guest listener exposes **only** guest and
health routes — admin endpoints are unreachable by design.

## Technical Context

**Language/Version**: Python 3.12+ (type-annotated, mypy-enforced)
**Primary Dependencies**: FastAPI, Uvicorn, SQLModel, Pydantic, Jinja2, s6-overlay (from HA base image)
**Storage**: SQLite via SQLModel ORM (`/data/captive_portal.db`)
**Testing**: pytest (unit, integration, contract, performance markers); pytest-asyncio; ruff + mypy for static analysis
**Target Platform**: Home Assistant OS / Supervised — Linux amd64 & aarch64 (Docker container with s6-overlay)
**Project Type**: Home Assistant add-on (web service — FastAPI ASGI)
**Performance Goals**: 50 concurrent captive detection requests without degradation; voucher redemption <800 ms p95; captive detection redirect <1 s
**Constraints**: Must not break existing ingress listener; admin routes must be completely unreachable on guest port; guest port configurable via HA `ports` mapping only (no duplicate schema option)
**Scale/Scope**: ~50 simultaneous guests per property; 7+ captive detection endpoints; ~15 route modules split across two listeners

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will have docstrings, type annotations, pass ruff/mypy. SPDX headers on every new file. |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | Red-Green-Refactor for every unit of production code. Existing tests must not be modified. |
| III | User Experience Consistency | ✅ PASS | Guest portal experience unchanged. Admin UI unchanged (ingress backward compat). Captive detection redirects work across all platforms. |
| IV | Performance Requirements | ✅ PASS | Captive detection: <1 s redirect. 50 concurrent requests target. Rate limiting on guest authorization (5/60 s per IP). |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | One logical change per commit. SPDX headers. DCO sign-off. Conventional Commits. Pre-commit hooks. |
| VI | Phased Development | ✅ PASS | Plan defines clear phases: research → design → tasks. Each phase delivers testable increment. |

**Gate Result**: ✅ ALL GATES PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/004-dual-port-networking/
├── plan.md              # This file
├── research.md          # Phase 0 output — technology decisions
├── data-model.md        # Phase 1 output — entities & route policy
├── quickstart.md        # Phase 1 output — developer onboarding
├── contracts/           # Phase 1 output — guest listener API contracts
│   └── guest-api.md     # Guest-facing endpoint contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks, not this command)
```

### Source Code (repository root)

```text
addon/
├── config.yaml                           # Updated: add 8099/tcp port + guest_external_url schema
├── rootfs/etc/s6-overlay/s6-rc.d/
│   ├── captive-portal/                   # Existing: ingress listener (port 8080)
│   │   ├── run                           # Unchanged
│   │   ├── finish                        # Unchanged
│   │   └── type                          # Unchanged (longrun)
│   ├── captive-portal-guest/             # NEW: guest listener (port 8099)
│   │   ├── run                           # NEW: starts uvicorn on 8099 with guest app
│   │   ├── finish                        # NEW: logs abnormal exit
│   │   ├── type                          # NEW: longrun
│   │   └── dependencies.d/              # NEW: (empty — no inter-service dep)
│   └── user/contents.d/
│       ├── captive-portal                # Existing
│       └── captive-portal-guest          # NEW: register guest service
├── src/captive_portal/
│   ├── app.py                            # Updated: refactor route registration for reuse
│   ├── guest_app.py                      # NEW: guest-only FastAPI app factory
│   ├── config/
│   │   └── settings.py                   # Updated: add guest_port, guest_external_url fields
│   ├── api/routes/
│   │   ├── captive_detect.py             # Updated: use external URL for guest listener redirects
│   │   ├── guest_portal.py              # Updated: use external URL for guest listener redirects
│   │   ├── health.py                    # Reused on both listeners (may add cross-listener check)
│   │   └── [admin routes unchanged]
│   └── security/
│       └── rate_limiter.py              # Existing: already in place for guest routes
└── Dockerfile                            # Updated: chmod +x guest run script

tests/
├── unit/
│   ├── test_guest_app_factory.py         # NEW: guest app route isolation tests
│   ├── test_guest_app_routes.py          # NEW: verify admin routes absent on guest app
│   └── config/
│       └── test_settings_guest.py        # NEW: guest_external_url & port config tests
├── integration/
│   ├── test_dual_port_isolation.py       # NEW: admin routes unreachable on guest port
│   ├── test_guest_listener_health.py     # NEW: health endpoints on guest listener
│   ├── test_captive_detect_guest.py      # NEW: captive detection on guest listener
│   └── test_guest_external_url.py        # NEW: redirect URL generation tests
└── [existing tests unchanged]
```

**Structure Decision**: Single project / single package. The guest listener is a
second uvicorn process serving a stripped-down FastAPI app (`guest_app.py`) that
mounts only guest, captive-detection, and health routers from the existing
codebase.  No new packages, no monorepo split.  The two services share the same
installed Python package but run independent uvicorn processes under s6-overlay.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Constitution Re-Check (Post-Design)

*Re-evaluated after Phase 1 design artifacts are complete.*

| # | Principle | Status | Design Impact |
|---|-----------|--------|---------------|
| I | Code Quality (NON-NEGOTIABLE) | ✅ PASS | `guest_app.py` has full docstrings and type annotations. All new s6 scripts have SPDX headers. Settings validation follows existing patterns. |
| II | Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | New test files defined for guest app factory, route isolation, health, captive detection, and external URL. Existing tests remain unchanged (FR-016). |
| III | User Experience Consistency | ✅ PASS | Guest portal templates and themes are shared between both apps. Captive detection redirects use same patterns. Admin UI completely unchanged. |
| IV | Performance Requirements | ✅ PASS | No new middleware on hot paths. Guest app has lighter middleware stack (no SessionMiddleware). Shared SQLite DB handles concurrent reads. Rate limiting preserved. |
| V | Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | Implementation will follow: s6 service files → guest app factory → settings update → config.yaml update → captive detect update → tests. Each is an atomic commit. |
| VI | Phased Development | ✅ PASS | Tasks (Phase 2) will define incremental phases: infrastructure (s6 + config) → guest app factory → route integration → captive detection → health → testing. |

**Post-Design Gate Result**: ✅ ALL GATES PASS — ready for Phase 2 task generation.
