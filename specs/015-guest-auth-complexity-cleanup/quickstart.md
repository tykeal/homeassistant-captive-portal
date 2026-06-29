SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0

# Quickstart: Guest Auth Complexity Cleanup

**Feature**: 015-guest-auth-complexity-cleanup
**Date**: 2026-06-29
**Branch**: `015-guest-auth-plan` (plan-only branch for feature
`015-guest-auth-complexity-cleanup`)

## Operator Impact

No operator action is required. This feature is an internal,
behavior-preserving refactor of guest authorization code. It must not add
settings, change database schema, change Home Assistant or Omada controller
configuration, alter guest pages, alter redirects, alter cookies, or alter audit
entries.

## Developer Workflow

1. Start from current `main` with the feature-014 characterization suite green.
2. Add focused assertions only for extracted units not already pinned by feature
   014 characterization tests.
3. Move `_handle_get_submission` and `_process_authorization` into
   `guest_authorization/orchestration.py`.
4. Split `_process_authorization` into preparation, decision dispatch,
   controller finalization, controller failure, and success helpers.
5. Add frozen internal dataclasses for voucher/booking decision context,
   booking grant creation, and booking audit failures.
6. Refactor `authorize_booking`, `_create_booking_grant`,
   `_audit_booking_error`, and `authorize_voucher` to use those objects.
7. Run the same characterization tests after each extraction step.
8. Refresh the `.aislop` baseline only during implementation after the six issue
   #189 findings are absent.
9. Stop if any guest HTTP response, audit entry, grant field, controller call,
   redirect, header, or cookie differs unexpectedly.

## Targeted Characterization Coverage

Reuse the feature-014 coverage for:

- `/guest/authorize` form rendering with Omada query parameters.
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
  tests/utils/test_guest_portal_characterization.py \
  tests/integration/test_guest_portal_form_flow.py \
  tests/integration/test_guest_portal_full_rendering.py \
  tests/integration/test_guest_authorization_flow_voucher.py \
  tests/integration/test_guest_authorization_flow_booking.py \
  tests/integration/test_guest_external_url.py \
  tests/integration/test_post_auth_redirect_fallback.py \
  tests/integration/test_post_auth_redirect_original_destination.py \
  tests/integration/test_post_auth_redirect_whitelist.py \
  tests/integration/test_guest_security_headers.py \
  tests/integration/test_vlan_voucher_authorization.py \
  tests/integration/test_vlan_booking_authorization.py \
  tests/unit/routes/test_guest_authorization_context.py \
  tests/unit/routes/test_guest_authorization_controller.py \
  tests/unit/routes/test_guest_authorization_errors.py \
  tests/unit/routes/test_guest_authorization_form.py \
  tests/unit/routes/test_guest_authorization_redirects.py \
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

Before merge, run the repository pre-commit hooks and confirm the staged aislop
complexity gate reports no active issue #189 findings.

## Golden Normalization Rules

- Replace CSRF token values with `<csrf-token>` only after asserting token
  presence and accepted source.
- Freeze time where possible; otherwise replace generated timestamp strings
  with `<timestamp>` after asserting format and ordering that matters.
- Replace generated grant IDs and controller grant IDs with deterministic
  placeholders while preserving cookie/header names and attributes.
- Normalize audit timestamps only; actor, action, outcome, target, and metadata
  keys/values must remain exact.
- Do not normalize stable HTML, status codes, response headers, redirect
  locations, error messages, audit metadata, controller payload fields, or grant
  field values.

## Completion Criteria

The implementation stage is complete only when:

1. The feature-014 characterization suite passes before refactoring.
2. The same characterization tests pass unchanged after refactoring.
3. New assertions cover any extracted unit not already pinned.
4. `guest_portal.py` is below 400 lines.
5. `_process_authorization` and `authorize_booking` are at or below 80 lines.
6. `authorize_booking`, `_create_booking_grant`, `_audit_booking_error`, and
   `authorize_voucher` have six parameters or fewer.
7. Ruff reports no C901 violation and no new `# noqa` suppressions exist.
8. Mypy, interrogate, REUSE, pre-commit, CI, and Copilot review is clean.
9. The `.aislop` baseline refresh is limited to the cleared issue #189 state.
