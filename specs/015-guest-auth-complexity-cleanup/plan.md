SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Guest Auth Complexity Cleanup

**Branch**: `015-guest-auth-plan` (plan-only branch for feature
`015-guest-auth-complexity-cleanup`) | **Date**: 2026-06-29 |
**Spec**: [spec.md](./spec.md)
**Input**: Feature specification from
`/specs/015-guest-auth-complexity-cleanup/spec.md`

## Summary

Clear the six issue #189 guest-authorization complexity findings without
changing guest behavior. The plan keeps FastAPI route signatures intact, moves
shared authorization orchestration out of `guest_portal.py`, splits the
remaining long helpers into cohesive internal units, and collapses helper
parameter counts with frozen in-memory dataclasses. Feature 014's guest portal
characterization suite remains the primary safety net; new assertions are added
only for extracted units that are not already pinned.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLModel, Home Assistant add-on runtime,
TP-Omada controller adapters, `uv` dependency management
**Storage**: Existing SQLModel tables only; no schema or migration changes
**Testing**: `uv run pytest`, ruff, mypy, interrogate, REUSE, staged aislop
**Target Platform**: Linux Home Assistant add-on container
**Project Type**: Python FastAPI web service / HA add-on
**Performance Goals**: Preserve current authorization latency and avoid new
blocking calls in the request path
**Constraints**: Byte-equivalent guest-auth HTTP contract, redirects, headers,
cookies, audit metadata, grant persistence, controller calls, no route-signature
change, no new `# noqa`, no `portal_settings_ui.py` work
**Scale/Scope**: Limited to `addon/src/captive_portal/api/routes/guest_portal.py`,
`addon/src/captive_portal/api/routes/guest_authorization/`, guest authorization
tests, and the implementation-phase `.aislop` baseline refresh

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-research gate

- **Code Quality**: PASS. The implementation plan targets existing C901,
  function-length, file-size, and parameter-count findings without adding
  suppressions.
- **Test-Driven Development**: PASS. The plan reuses the feature-014
  characterization suite before refactoring and adds assertions only before
  extracting units that lack coverage.
- **User Experience Consistency**: PASS. Guest pages, messages, redirects,
  cookies, security headers, audit entries, and controller payloads are
  preserved.
- **Performance Requirements**: PASS. The refactor only changes internal helper
  boundaries and keeps async controller and service calls in the same order.
- **Atomic Commits & Compliance**: PASS. This plan stage produces one signed
  documentation commit with SPDX headers and no implementation changes.
- **Phased Development**: PASS. This PR stops at plan artifacts; tasks and
  implementation are deferred to later speckit stages.

### Post-design gate

- **Code Quality**: PASS. The design moves `_handle_get_submission` and
  `_process_authorization` to a guest-authorization orchestration module,
  extracts smaller helper steps, and introduces frozen dataclasses that reduce
  the named helper signatures to six parameters or fewer.
- **Test-Driven Development**: PASS. Quickstart validation requires the 014
  characterization suite to pass before and after each extraction, with focused
  unit assertions for the new param objects and split helpers when needed.
- **User Experience Consistency**: PASS. The contract artifact explicitly
  reaffirms `/guest/authorize`, `/guest/welcome`, and `/guest/error` behavior.
- **Performance Requirements**: PASS. No new I/O, database queries, sleeps, or
  controller calls are introduced by the design.
- **Atomic Commits & Compliance**: PASS. Artifacts are plan-only and carry SPDX
  headers.
- **Phased Development**: PASS. Phase 0 and Phase 1 artifacts are complete;
  `tasks.md` is intentionally not created during this stage.

## Project Structure

### Documentation (this feature)

```text
specs/015-guest-auth-complexity-cleanup/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── guest-http-contract.md
```

### Source Code (repository root)

```text
addon/src/captive_portal/api/routes/
├── guest_portal.py
└── guest_authorization/
    ├── __init__.py
    ├── bookings.py
    ├── context.py
    ├── controller.py
    ├── errors.py
    ├── form.py
    ├── mac_address.py
    ├── orchestration.py        # planned internal split target
    ├── redirects.py
    └── vouchers.py

tests/
├── integration/
│   ├── test_guest_authorization_flow_booking.py
│   ├── test_guest_authorization_flow_voucher.py
│   ├── test_guest_portal_form_flow.py
│   └── test_guest_portal_full_rendering.py
├── unit/routes/
│   ├── test_guest_authorization_context.py
│   ├── test_guest_authorization_controller.py
│   ├── test_guest_authorization_errors.py
│   ├── test_guest_authorization_form.py
│   ├── test_guest_authorization_redirects.py
│   ├── test_guest_portal_mac_extraction.py
│   ├── test_guest_portal_omada.py
│   ├── test_guest_portal_omada_errors.py
│   └── test_guest_portal_omada_params.py
└── utils/
    ├── guest_portal_characterization.py
    └── test_guest_portal_characterization.py
```

**Structure Decision**: Use the existing feature-014
`guest_authorization/` package as the refactor boundary. Keep only FastAPI
route declarations, route-visible dependency functions, template setup, and
thin calls to orchestration helpers in `guest_portal.py`. Move shared GET/POST
authorization orchestration and its direct private helpers into the helper
package.

## Complexity Tracking

No constitution violations are introduced or justified. The implementation must
remove the six issue #189 findings instead of accepting complexity debt.

| Finding | Current live source | Planned design response |
|---------|---------------------|-------------------------|
| `guest_portal.py` file too large | 565 lines, limit 400 | Move `_handle_get_submission`, `_process_authorization`, and direct helper steps into `guest_authorization/orchestration.py`, leaving the route module below 400 lines. |
| `_process_authorization` too long | 148 lines, limit 80 | Split into CSRF/rate/MAC setup, decision dispatch, controller finalization, failure audit, and success redirect helpers. |
| `authorize_booking` too long and too many params | 163 lines, 7 params | Pass a frozen decision context and extract integration lookup, VLAN denial, grant creation, and error mapping helpers. |
| `_create_booking_grant` too many params | 8 params | Replace scalar grant inputs with a frozen `BookingGrantInput`. |
| `_audit_booking_error` too many params | 9 params | Replace repeated audit inputs with frozen `BookingAuditContext` and `BookingAuditFailure`. |
| `authorize_voucher` too many params | 7 params | Pass the shared frozen decision context used by booking authorization. |
