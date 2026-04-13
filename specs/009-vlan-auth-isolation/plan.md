SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: VLAN-Based Authorization Isolation

**Branch**: `009-vlan-auth-isolation` | **Date**: 2025-07-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-vlan-auth-isolation/spec.md`

## Summary

Add VLAN-based authorization isolation to the captive portal so that each Rental Control integration maps to specific guest VLAN(s), and each authorization attempt validates the connecting device's VLAN ID against the configured allowlist. Vouchers optionally receive VLAN restrictions. Integrations and vouchers without VLAN configuration continue to work unrestricted (backward compatible). The `vid` parameter is already captured from the Omada controller redirect and stored on `AccessGrant.omada_vid` — this feature adds the missing validation layer between that captured VID and per-integration/per-voucher VLAN allowlists.

**Technical approach**: Add an `allowed_vlans` JSON column to `HAIntegrationConfig` and `Voucher` models to store per-entity VLAN allowlists. Create a `VlanValidationService` to enforce VLAN matching during authorization. Insert VLAN validation into the existing `handle_authorization()` flow after code validation but before controller authorization. Extend admin API and UI for VLAN configuration management. Record VLAN validation decisions in the audit log.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI, httpx, SQLModel, Pydantic, uvicorn, argon2-cffi, Jinja2
**Storage**: SQLite via SQLModel (ORM), path: `/data/captive_portal.db`
**Testing**: pytest + pytest-asyncio, ruff (linting), mypy (strict), interrogate (docstrings)
**Target Platform**: Linux (Home Assistant OS / Supervisor addon), amd64 + aarch64
**Project Type**: Web service (dual-port FastAPI addon for Home Assistant)
**Performance Goals**: Voucher redemption < 800ms p95 @ 50 concurrent; VLAN validation adds < 5ms per request (single DB lookup)
**Constraints**: No blocking calls on event loop; backward-compatible upgrade; error messages must not leak VLAN IDs or network topology
**Scale/Scope**: ~4,600 LOC Python, 20 API route modules, 12 services; typically < 20 integrations, < 100 vouchers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will have docstrings, type annotations, pass ruff/mypy/interrogate. VLAN validation logic is simple comparison — no function will exceed CC 10. SPDX headers on all new files. |
| II. Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | Each VLAN validation rule maps to a specific acceptance scenario from the spec. Unit tests for VlanValidationService, integration tests for the full authorization flow with VLAN checks. Red-green-refactor cycle enforced. |
| III. User Experience Consistency | ✅ PASS | Guest error message is vague by design ("This code is not valid for your network") per FR-004 — does not reveal VLAN IDs. Admin UI follows existing integration config page patterns. API contracts will be documented. |
| IV. Performance Requirements | ✅ PASS | VLAN validation is an in-memory set comparison after a single DB column read. No additional network I/O. Well under performance budgets. |
| V. Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | Model changes, service logic, route wiring, admin API, admin UI, tests, and docs each map to separate atomic commits. SPDX, DCO sign-off, Conventional Commits enforced. |
| VI. Phased Development | ✅ PASS | 4 phases: data model → validation service → admin API/UI → voucher VLAN support. Each independently testable. |
| Security: Secrets | ✅ PASS | No new secrets. Error messages do not expose VLAN IDs to end users per spec assumption. |
| Observability | ✅ PASS | FR-010 requires audit log entries for every VLAN validation with the VID and allowlist recorded. Structured logging for all VLAN decisions. |

**Pre-Phase 0 Gate**: ✅ ALL PASS — no violations, no complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/009-vlan-auth-isolation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── vlan-validation-api.md
│   └── admin-integration-vlan-api.md
└── tasks.md             # Phase 2 output (NOT created by plan)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── models/
│   ├── ha_integration_config.py     # +allowed_vlans JSON column
│   └── voucher.py                   # +allowed_vlans JSON column
├── services/
│   └── vlan_validation_service.py   # NEW — VLAN allowlist enforcement
├── api/routes/
│   ├── guest_portal.py              # +VLAN validation in handle_authorization()
│   ├── integrations.py              # +allowed_vlans in create/update/response schemas
│   └── vouchers.py                  # +allowed_vlans in create/response schemas
├── persistence/
│   └── database.py                  # +migration for allowed_vlans columns
└── web/templates/admin/
    ├── integrations.html            # +VLAN configuration UI section
    └── vouchers.html                # +optional VLAN restriction UI

tests/
├── unit/
│   ├── services/
│   │   └── test_vlan_validation_service.py   # NEW — core validation logic
│   └── models/
│       ├── test_ha_integration_config_vlans.py  # NEW — model validation
│       └── test_voucher_vlans.py                # NEW — model validation
├── integration/
│   ├── test_vlan_booking_authorization.py     # NEW — booking + VLAN flow
│   ├── test_vlan_voucher_authorization.py     # NEW — voucher + VLAN flow
│   └── test_vlan_backward_compatibility.py    # NEW — no-VLAN-config path
└── unit/routes/
    └── test_integrations_vlan_api.py          # NEW — admin API VLAN endpoints
```

**Structure Decision**: Existing single-project addon structure. All changes integrate into established modules. One new service file (`vlan_validation_service.py`) follows the existing service pattern. No structural reorganization needed.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Post-Phase 1 Constitution Re-Check

| Principle | Status | Design Impact |
|-----------|--------|---------------|
| I. Code Quality | ✅ PASS | `VlanValidationService` is a simple stateless class with < 5 methods. JSON column uses established `sa_column=Column(JSON)` pattern from `AuditLog.meta`. All new code will have docstrings, type annotations, SPDX headers. No function exceeds CC 10. |
| II. TDD | ✅ PASS | Each acceptance scenario from the spec maps to a specific test case. VlanValidationService has 10+ unit test cases covering all parse/validate branches. Integration tests cover the full authorization flow. Red-green-refactor enforced. |
| III. UX Consistency | ✅ PASS | Guest error messages are deliberately vague ("This code is not valid for your network") — no VLAN IDs leaked. Admin UI extends the existing integrations page with consistent styling. API schema extensions follow established patterns. |
| IV. Performance | ✅ PASS | VLAN validation is an in-memory set membership check after loading the integration/voucher (which is already loaded for code validation). Zero additional DB queries for the validation itself. Well under 800ms p95 budget. |
| V. Atomic Commits | ✅ PASS | Changes decompose cleanly: (1) model + migration, (2) validation service + tests, (3) route wiring + tests, (4) admin API + tests, (5) admin UI, (6) voucher VLAN + tests, (7) backward compat tests. Each is a single logical commit. |
| VI. Phased Development | ✅ PASS | 4 phases: data model → core validation → admin API/UI → voucher support. Each phase delivers independently testable increment. Phase boundaries documented. |
| Security | ✅ PASS | Error messages do not expose VLAN IDs or network topology to end users. VLAN configuration requires admin authentication. No new secrets or credentials. |
| Observability | ✅ PASS | Every VLAN decision logged in audit trail with device VID, allowlist, and result. Structured logging for validation failures. |

**Post-Design Gate**: ✅ ALL PASS — design is constitution-compliant. Ready for Phase 2 task generation.
