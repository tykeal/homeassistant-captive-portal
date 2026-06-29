SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Guest Portal Decomposition

**Feature**: 014-guest-portal-decomposition
**Date**: 2026-06-28
**Branch**: `014-guest-portal-decomposition`

## Operator Impact

No operator action is required. This feature is a behavior-preserving internal
refactor of the guest authorization implementation. It must not add settings,
change database schema, change controller configuration, or alter guest-facing
pages, redirects, cookies, headers, audit entries, or controller calls.

## Developer Workflow

1. Start from the pre-refactor implementation on the feature branch.
2. Add characterization tests for the current guest authorization behavior.
3. Run the characterization tests and confirm they pass before moving code.
4. Extract one cohesive helper group at a time from `guest_portal.py`.
5. After each extraction, run the same characterization tests unchanged.
6. Remove `# noqa: C901` from `show_authorize_form` and
   `_process_authorization` only after ruff passes.
7. Run the full targeted guest regression set and repository quality gates.

## Targeted Characterization Coverage

The pre-refactor and post-refactor runs should cover:

- `/guest/authorize` form rendering with all Omada query parameters.
- GET submissions with `code` and `csrf_token` query parameters.
- POST submissions with form fields and CSRF form/header handling.
- CSRF missing, malformed, expired, tampered, Origin mismatch, and Referer
  mismatch failures.
- MAC extraction from headers, form data, query parameters, dash-separated Omada
  values, missing values, and invalid values.
- Voucher success, invalid code, expiry/revocation, device limit, duplicate
  device behavior, and VLAN denial.
- Booking success, no integration, not found, outside window, duplicate active
  grant, grace-period handling, case-preserved identifiers, and VLAN denial.
- Controller success, no configured adapter, legacy site override, controller
  rejection, and retry exhaustion.
- Redirect behavior for safe continue URLs, unsafe URLs, missing continue URLs,
  root paths, retry links, and open-redirect protections.
- Security headers, no-store cache behavior, referrer policy, and `grant_id`
  cookie attributes.
- Audit metadata for success, denied, rate-limited, MAC failure, VLAN failure,
  integration unavailable, and controller failure outcomes.

## Suggested Targeted Commands

Run from the repository root after dependencies are available:

```bash
uv run pytest \
  tests/integration/test_guest_portal_form_flow.py \
  tests/integration/test_guest_authorization_flow_voucher.py \
  tests/integration/test_guest_authorization_flow_booking.py \
  tests/integration/test_guest_external_url.py \
  tests/integration/test_post_auth_redirect_fallback.py \
  tests/integration/test_post_auth_redirect_original_destination.py \
  tests/integration/test_post_auth_redirect_whitelist.py \
  tests/integration/test_guest_security_headers.py \
  tests/integration/test_vlan_voucher_authorization.py \
  tests/integration/test_vlan_booking_authorization.py \
  tests/unit/routes/test_guest_portal_mac_extraction.py \
  tests/unit/routes/test_guest_portal_omada.py \
  tests/unit/routes/test_guest_portal_omada_errors.py \
  tests/unit/routes/test_guest_portal_omada_params.py \
  tests/unit/security/test_hmac_csrf.py \
  tests/unit/security/test_rate_limiter.py
```

Then run quality gates relevant to the changed code:

```bash
uv run ruff check addon/src/captive_portal/api/routes/ tests/
uv run mypy addon/src/captive_portal
uv run interrogate -vv --fail-under=100 addon/src/captive_portal tests
uv run reuse lint
```

Before merge, run the repository's configured pre-commit hooks and confirm the
staged `aislop` complexity gate reports no unhandled guest portal findings.

## Golden Normalization Rules

- Replace CSRF token values with `<csrf-token>` after asserting token presence
  and accepted source.
- Freeze time where possible; otherwise replace generated timestamp strings
  with `<timestamp>` after asserting format and relevant ordering.
- Replace generated grant IDs and controller grant IDs with deterministic
  placeholders while preserving cookie/header names and attributes.
- Normalize audit timestamps only; actor, action, outcome, target, and metadata
  keys/values must remain exact.
- Do not normalize stable HTML, status codes, response headers, redirect
  locations, error messages, audit metadata, controller payload fields, or grant
  field values.

## Completion Criteria

The implementation is complete only when:

1. Characterization tests pass before the refactor.
2. The same tests pass unchanged after the refactor.
3. Existing guest portal, authorization, redirect, security, Omada, and VLAN
   tests pass.
4. Ruff reports no C901 violation and no C901 suppressions remain on
   `show_authorize_form` or `_process_authorization`.
5. The complexity scanner reports no unhandled guest portal findings, or any
   remaining FastAPI route parameter finding is documented/baselined because
   changing it would risk the pinned HTTP contract.
6. Mypy, interrogate, REUSE, pre-commit, CI, and Copilot review are clean.
