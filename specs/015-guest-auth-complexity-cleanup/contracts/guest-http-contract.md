SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0

# Contract: Guest Authorization HTTP Behavior

**Feature**: 015-guest-auth-complexity-cleanup
**Date**: 2026-06-29
**Type**: External guest HTTP, audit, grant, and controller contract

## Source Contract

This feature reaffirms the feature-014 guest HTTP contract in
`specs/014-guest-portal-decomposition/contracts/guest-http-contract.md`. The
implementation must not change any stable externally observable behavior for:

- `GET /guest/authorize`
- `POST /guest/authorize`
- `GET /guest/welcome`
- `GET /guest/error`

The feature-014 contract remains the canonical detailed field-by-field
reference. This artifact records the additional preservation commitments for
the complexity cleanup plan.

## Invariants

- Route signatures, query aliases, form field names, required fields, optional
  fields, defaults, and validation behavior remain unchanged.
- Stable rendered HTML, hidden fields, response status codes, media types,
  security headers, cache headers, referrer policy, cookies, redirect
  `Location` values, and retry URLs remain byte-equivalent for identical input
  and fixture state.
- Dynamic CSRF tokens, generated grant IDs, timestamps, controller grant IDs,
  and audit timestamps may be normalized only by explicit characterization-test
  rules inherited from feature 014.
- CSRF validation, trusted-proxy client IP resolution, rate limiting, MAC
  extraction, code validation, voucher decisions, booking decisions, Omada
  metadata persistence, controller authorization, audit logging, and success
  redirects occur in the same observable order.
- Guest-visible errors remain sanitized HTML error responses where the current
  implementation renders HTML. Controller diagnostics remain audit/log details
  only and do not leak to guests.

## Authorization Preservation Matrix

| Area | Required preservation |
|------|-----------------------|
| GET form rendering | Omada query preservation, effective continue fallback, CSRF token generation, debug redaction, and security headers. |
| GET submissions | `code` plus `csrf_token` continues to authorize through the shared flow; missing optional session remains HTTP 503. |
| POST submissions | Existing form fields and dependency injection remain unchanged. |
| MAC extraction | Header, form, and query priority and error messages remain unchanged. |
| Voucher flow | Validation, lookup, VLAN denial, redemption, device limit, duplicate device, expiry, grant state, and audit metadata remain unchanged. |
| Booking flow | Integration lookup, not-found/error mappings, window/grace rules, duplicate detection, VLAN denial, grant fields, and audit metadata remain unchanged. |
| Controller flow | No-adapter activation, adapter payload, legacy site override, grant status transitions, controller grant ID, and failure handling remain unchanged. |
| Redirect/cookie flow | Safe continue handling, welcome fallback, HTTP 303, `grant_id` cookie attributes, and no-store/referrer headers remain unchanged. |
| `/guest/error` | Message sanitization, truncation, default message, retry URL, template, and security headers remain unchanged. |

## Out of Scope

- No new API contracts, database schemas, migrations, operator settings, or UI
  changes.
- No changes to `portal_settings_ui.py:110`; that finding remains tracked by
  issue #190.
- No route-signature changes and no new `# noqa` suppressions.
