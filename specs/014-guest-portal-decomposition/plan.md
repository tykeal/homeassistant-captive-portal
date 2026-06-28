SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Guest Portal Decomposition

**Branch**: `014-guest-portal-plan` | **Date**: 2026-06-28 |
**Spec**: `specs/014-guest-portal-decomposition/spec.md`
**Input**: Feature specification from
`/specs/014-guest-portal-decomposition/spec.md`

## Summary

Decompose the security-critical guest authorization route module without any
observable behavior change to `/guest/authorize` GET and POST,
`/guest/welcome`, or `/guest/error`. The implementation must first add
golden/characterization coverage for the current code, including normalized
CSRF tokens, timestamps, grant IDs, cookies, and audit timestamps, then move
cohesive logic out of `guest_portal.py` into directly related guest
authorization helpers.

The planned decomposition keeps FastAPI's public request contract intact while
moving current helper responsibilities into small units for request context,
MAC extraction, form/rendering, voucher authorization, booking authorization,
Omada metadata/controller authorization, redirect handling, and error/audit
support. The future implementation scope is intentionally limited to
`guest_portal.py`, directly extracted helpers, and characterization or
regression tests for the same behavior.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLModel, Jinja2 templates, pydantic,
uv-managed project dependencies, Home Assistant add-on runtime
**Storage**: Existing SQLite through SQLModel; `AccessGrant`, `Voucher`,
`HAIntegrationConfig`, and `RentalControlEvent` behavior is preserved with no
schema change
**Testing**: pytest, pytest-asyncio, ruff with C901, mypy strict,
interrogate 100%, REUSE, pre-commit, GitHub Actions CI, staged `aislop`
complexity checks
**Target Platform**: Linux Home Assistant add-on container and local FastAPI
service execution
**Project Type**: Single Python web service/add-on with separate admin and
guest FastAPI applications
**Performance Goals**: Preserve voucher redemption within 800 ms p95 at 50
concurrent requests and controller propagation within 25 seconds; avoid
blocking the FastAPI event loop
**Constraints**: Zero HTTP/audit/controller behavior change; characterization
coverage must pass before and after code movement; no feature, schema,
controller API, or settings changes; `portal_settings_ui.py:110` remains out
of scope
**Scale/Scope**: One oversized guest route module of about 1262 lines,
`_process_authorization` of about 546 lines, four guest routes, and the
existing guest portal and authorization test suite

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality**: PASS. The plan decomposes high-complexity guest
  authorization behavior into typed, documented helper modules. Future code
  must pass ruff C901 without `# noqa: C901` on `show_authorize_form` or
  `_process_authorization`, and must clear or explicitly baseline only those
  parameter findings that cannot safely change because of FastAPI contracts.
- **II. Test-Driven Development**: PASS. Production movement is blocked until
  characterization tests pin the current behavior. The same tests must remain
  unchanged and green after extraction.
- **III. User Experience Consistency**: PASS. Guest HTML, redirects, hidden
  fields, cookies, sanitized errors, security headers, and retry links are
  treated as contract artifacts rather than design variables.
- **IV. Performance Requirements**: PASS. The decomposition introduces no new
  I/O, database schema, controller API, or blocking work. Helper boundaries
  preserve existing async service calls and controller propagation behavior.
- **V. Atomic Commits & Compliance**: PASS. This PR is a single plan-only docs
  change with SPDX headers. Future implementation commits must be atomic,
  signed off, and must not bypass pre-commit.
- **VI. Phased Development**: PASS. The plan separates characterization,
  extraction, route simplification, complexity validation, and final regression
  phases. No implementation tasks are created during PLAN.

**Post-design re-check**: PASS. Research, data model, contracts, and
quickstart preserve all constitution gates. No product questions remain. The
only possible complexity waiver is a documented or baselined FastAPI route
parameter finding when reducing the signature would risk the pinned HTTP
contract.

## Project Structure

### Documentation (this feature)

```text
specs/014-guest-portal-decomposition/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── guest-http-contract.md
└── tasks.md             # Future /speckit.tasks output; not created now
```

### Source Code (repository root)

```text
addon/src/captive_portal/api/routes/
├── guest_portal.py              # Thin FastAPI route definitions only
└── guest_authorization/         # Directly extracted guest helpers
    ├── __init__.py
    ├── context.py               # Request, dependency, and Omada params
    ├── csrf.py                  # Guest CSRF coordination if needed
    ├── mac_address.py           # MAC extraction and normalization
    ├── form.py                  # Form rendering and hidden-field context
    ├── vouchers.py              # Voucher validation/redemption path
    ├── bookings.py              # Booking lookup/window/duplicate path
    ├── controller.py            # Omada site override and authorize call
    ├── redirects.py             # Success/fallback/retry destinations
    └── errors.py                # Sanitized errors and audit metadata helpers

tests/
├── integration/
│   ├── test_guest_portal_*      # Form/rendering/security behavior
│   ├── test_guest_authorization_flow_*
│   ├── test_guest_external_url.py
│   ├── test_post_auth_redirect_*.py
│   └── test_vlan_*_authorization.py
└── unit/
    ├── routes/test_guest_portal_*.py
    └── routes/test_guest_authorization_*.py
```

**Structure Decision**: Keep the existing single add-on project structure.
Place extracted helpers directly under `api/routes/guest_authorization/` so the
scope remains tied to the guest portal and does not become a broader service or
schema refactor. The public route module remains responsible for FastAPI
parameter declarations and delegates to typed internal request/dependency
objects.

## Source Behavior Inventory

Current `guest_portal.py` responsibilities that must be preserved:

- `_truncate`: strips empty values and bounds Omada metadata lengths.
- `_apply_site_override`: applies only valid 12-64 character hex site IDs to
  legacy Omada adapters.
- `_sanitize_error_message`: default error text, 500-character truncation,
  simple tag stripping, and fallback when empty.
- `_authorize_with_controller`: preserves no-adapter success, adapter authorize
  payload fields, `controller_grant_id`, FAILED status transitions, and
  diagnostic-only error details.
- `_extract_mac_address`: priority order is `X-MAC-Address`,
  `X-Client-Mac`, `Client-MAC`, submitted form MAC, then `clientMac` query;
  dash-separated Omada MACs normalize to colon form and invalid/missing MACs
  raise the current 400 details.
- `show_authorize_form`: GET submissions require both `code` and `csrf_token`;
  non-submissions render `guest/authorize.html`, preserve Omada query params,
  generate HMAC CSRF tokens, use GET forms, and choose effective continue from
  `continue`, `redirectUrl`, then root-path-aware `/guest/welcome`.
- `_handle_get_submission`: resolves the same dependencies and dependency
  override behavior used by GET submissions today.
- `_process_authorization`: validates CSRF, rate limits trusted-proxy client IP,
  extracts MAC, validates code type, executes voucher or booking flows,
  performs VLAN checks, applies Omada metadata and site override, authorizes on
  the controller, commits grant state, writes audit entries, clears successful
  rate limits, validates continue URLs, sets the `grant_id` cookie, and returns
  a 303 redirect.
- `handle_authorization`: preserves POST form names and aliases, dependency
  wiring, debug logging, and delegation into the shared authorization flow.
- `show_welcome` and `show_error`: render current templates with route-level
  security headers, root-path-aware retry URL, and sanitized error message.

## Phased Implementation Approach

1. **Characterization first**: Add golden tests that pass on the current module
   before any production movement. Cover GET form rendering, GET submission,
   POST submission, voucher success/denial, booking success/denial, CSRF
   sources/failures, MAC extraction, Omada parameter pass-through, redirects,
   error pages, security headers, controller success/failure, and audit/grant
   outcomes. Normalize only intentionally dynamic CSRF tokens, timestamps,
   grant IDs, cookies, and audit timestamps.
2. **Introduce internal context objects**: Add typed dataclasses or dependency
   models for Omada request metadata, authorization dependencies, and flow
   outcomes. Keep FastAPI route field names, aliases, defaults, optionality,
   and validation behavior unchanged.
3. **Extract low-risk helpers**: Move `_truncate`, `_apply_site_override`,
   `_sanitize_error_message`, `_extract_mac_address`, form context building,
   retry URL building, and redirect construction with import compatibility
   tests as needed.
4. **Extract controller authorization**: Move controller site override and
   `_authorize_with_controller` behavior into a controller helper while
   preserving no-adapter success and controller error transitions exactly.
5. **Split authorization decisions**: Extract voucher and booking flows into
   focused helpers that return the same grant, VLAN metadata, errors, and audit
   intent currently emitted inline. Keep `VoucherService`,
   `BookingCodeValidator`, `VlanValidationService`, and repository usage
   behavior unchanged.
6. **Thin route orchestration**: Replace `_process_authorization` with a small
   orchestrator that calls the extracted units in the current order. Remove
   C901 suppressions from `show_authorize_form` and `_process_authorization`
   only after ruff verifies complexity.
7. **Quality gates**: Run the characterization suite unchanged, existing guest
   portal/authorization/redirect/security/VLAN tests, ruff, mypy, interrogate,
   REUSE, and staged complexity checks. Document or baseline only a route
   parameter finding that cannot safely be reduced without changing FastAPI's
   HTTP contract.

## Complexity Tracking

No constitution violations are accepted for the target implementation. The
planned helper extraction is expected to clear `complexity/file-too-large` for
`guest_portal.py`, `complexity/function-too-long` for
`_process_authorization`, and C901 suppressions on `show_authorize_form` and
`_process_authorization`.

| Finding | Planned Resolution | Contract Safety Rule |
|---------|--------------------|----------------------|
| `guest_portal.py` file too large | Move only directly related guest authorization helpers under `api/routes/guest_authorization/` | No unrelated route, admin, settings, or schema code moves |
| `_process_authorization` too long/C901 | Split into CSRF/rate-limit, MAC, decision, controller, audit, and redirect helpers | Preserve current order and error mapping |
| `show_authorize_form` C901/noqa | Extract submission detection, debug logging, Omada param context, and template context helpers | Keep GET query aliases and response rendering unchanged |
| Guest route too many params | Reduce internal calls using typed grouping/dependencies where safe | Do not remove, rename, retype, or change FastAPI-visible fields |
| Unsafe route signature reduction | Document or baseline with link to the pinned HTTP contract | Allowed only if keeping the finding is safer than changing behavior |
