SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: Guest Portal HTTP Behavior

**Feature**: 014-guest-portal-decomposition
**Date**: 2026-06-28
**Type**: External guest HTTP, audit, grant, and controller contract

## Common Rules

- The routes covered by this contract are `/guest/authorize` GET and POST,
  `/guest/welcome`, and `/guest/error`.
- Stable response bodies, headers, cookies, redirect locations, media types,
  status codes, hidden fields, audit entries, persisted grant fields, and
  controller calls must match the pre-refactor implementation.
- Dynamic CSRF tokens, timestamps, generated grant IDs, cookies containing grant
  IDs, controller grant IDs, and audit timestamps may be normalized only by
  explicit characterization-test rules.
- Guest errors render HTML error pages through the current error handling path;
  they are not converted to raw JSON for guest flows.

## `GET /guest/authorize` Form Rendering

### Accepted query fields

| Query field | Alias behavior | Current use |
|-------------|----------------|-------------|
| `clientMac` | accepted as `client_mac` route value | Hidden field, MAC retry context |
| `clientIp` | accepted as `client_ip` route value | Hidden field/debug context |
| `site` | accepted as `site` | Hidden field, retry URL, legacy site override after submission |
| `apMac` | accepted as `ap_mac` | Hidden field, grant/controller metadata |
| `gatewayMac` | accepted as `gateway_mac` | Hidden field, grant/controller metadata |
| `radioId` | accepted as `radio_id` | Hidden field, grant/controller metadata |
| `ssidName` | accepted as `ssid_name` | Hidden field, grant/controller metadata |
| `vid` | accepted as `vid` | Hidden field, VLAN/grant/controller metadata |
| `t` | accepted as `t` | Hidden field pass-through |
| `redirectUrl` | accepted as `redirect_url` | Effective continue fallback |
| `continue` | accepted as `continue_url` | Effective continue and success redirect |
| `code` | accepted as `code` | GET submission detection |
| `csrf_token` | accepted as `csrf_token` | GET submission detection and CSRF validation |

### Rendering contract

- If both `code` and `csrf_token` are non-empty, the request is a
  submission and follows the authorization contract below.
- Otherwise the route renders `guest/authorize.html` with HTTP 200.
- `omada_params` contains only the current template Omada keys with empty
  string defaults: `clientMac`, `clientIp`, `site`, `apMac`, `gatewayMac`,
  `radioId`, `ssidName`, `vid`, `t`, and `redirectUrl`. `continue`, `code`,
  and `csrf_token` remain separate from `omada_params`.
- `continue_url` in the template is chosen in this order: `continue`,
  `redirectUrl`, root-path-aware `/guest/welcome`.
- A fresh HMAC guest CSRF token is generated for the form.
- The form continues to submit by GET and includes hidden fields for the current
  Omada metadata and `continue` alias.
- Route-level security headers include the current CSP fallback,
  `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin`, and `Cache-Control: no-store`.
- Debug logging redacts `code` and `csrf_token` values.

## `GET /guest/authorize` Submission

A GET request with non-empty `code` and `csrf_token` follows the same
authorization behavior as POST, with query parameters as the source of submitted
fields. If the optional database session cannot be created, the route raises
HTTP 503 with detail `Service temporarily unavailable.`

## `POST /guest/authorize` Submission

### Accepted form fields

| Form field | Required | Current use |
|------------|----------|-------------|
| `code` | yes | Voucher or booking code |
| `continue_url` | no | Success redirect candidate |
| `client_mac` | no | MAC extraction after headers |
| `site` | no | Retry URL and legacy site override |
| `gateway_mac` | no | Grant/controller metadata |
| `ap_mac` | no | Grant/controller metadata |
| `vid` | no | VLAN/grant/controller metadata |
| `ssid_name` | no | Grant/controller metadata |
| `radio_id` | no | Grant/controller metadata |
| `csrf_token` | yes by CSRF validator | CSRF validation |

### Authorization sequence

The current observable order is preserved:

1. Build `request.state.retry_query` only from the current non-empty retry
   keys: `clientMac`, `site`, `gatewayMac`, `apMac`, `vid`, `ssidName`,
   `radioId`, and `continue`. Do not add `clientIp`, `t`, or `redirectUrl`
   to retry links.
2. Validate guest CSRF token from the current supported sources: GET query for
   GET submissions, POST form for POST submissions, and `X-CSRF-Token` header
   according to `HMACCSRFProtection` behavior.
3. Resolve trusted-proxy-aware client IP from `PortalConfig` trusted networks.
4. Enforce rate limiting. Denials log `outcome="rate_limited"`, raise 429,
   and include the current `Retry-After` header.
5. Extract and validate MAC address.
6. Validate the submitted code through `UnifiedCodeService.validate_code`.
7. Execute voucher or booking authorization behavior.
8. Store truncated Omada metadata on the grant.
9. Apply valid legacy site override only to `OmadaLegacyAdapter`.
10. Authorize with the configured controller adapter or mark active when no
    adapter is configured.
11. Commit and refresh the grant.
12. On controller failure, audit the failure and raise 502 with the current
    user-facing message.
13. On success, clear the rate limit, audit success, validate `continue_url`,
    and return a 303 redirect with a `grant_id` cookie.

## MAC Extraction Contract

Priority order is fixed:

1. `X-MAC-Address` header.
2. `X-Client-Mac` header.
3. `Client-MAC` header.
4. Submitted form MAC when non-empty after stripping.
5. `clientMac` query parameter.

Dash-separated Omada MACs normalize to colon-separated uppercase form via
`validate_mac_address`. Missing MAC raises HTTP 400 with the current captive
portal guidance. Invalid MAC raises HTTP 400 with detail beginning
`Invalid MAC address format:`.

## Voucher Decision Contract

Voucher behavior preserves:

- Code normalization and invalid-format 400 behavior.
- Voucher lookup and redemption through `VoucherService`.
- VLAN validation before redemption when a voucher is found.
- VLAN denial audit outcome, target, metadata, HTTP 403, and generic message.
- Device-limit HTTP 410 and audit metadata.
- Voucher redemption error HTTP 410 and audit metadata.
- Grant persistence, voucher status effects, duplicate-device behavior, start
  and end timestamps, and user-facing text.

## Booking Decision Contract

Booking behavior preserves:

- Lookup across all configured `HAIntegrationConfig` rows.
- Missing integration HTTP 503 and error audit metadata.
- Booking-not-found HTTP 404 and denied audit metadata.
- VLAN validation against the matched integration only.
- Early check-in window of 60 minutes before start.
- End time plus integration checkout grace minutes.
- Duplicate active grant detection by MAC and case-insensitive booking ref.
- `floor_to_minute(max(now, start_utc))` for grant start and
  `ceil_to_minute(effective_end)` for grant end.
- Case-preserved booking identifier stored on the grant.
- Guest original input stored as `user_input_code`.
- Matched `integration_id` stored on the grant.
- Existing HTTP 403 and 409 mappings for outside-window and duplicate grants.

## Controller Authorization Contract

- With no adapter, pending grants become ACTIVE and no controller call occurs.
- With an adapter, `authorize` receives MAC, grant expiry, gateway MAC, AP MAC,
  SSID name, radio ID, and VLAN ID exactly as current truncated values.
- Successful controller results mark the grant ACTIVE and store `grant_id` from
  the returned dictionary as `controller_grant_id`.
- `OmadaClientError` and `OmadaRetryExhaustedError` mark the grant FAILED,
  log diagnostics, return diagnostic detail for audit only, and lead to the
  current HTTP 502 guest-facing message.
- Legacy site override accepts only non-empty values matching the current
  12-64 character hex pattern and leaves other adapters unchanged.

## Redirect and Cookie Contract

- Safe `continue_url` values are used as the success redirect destination.
- Unsafe, missing, or rejected `continue_url` values fall back to root-path-aware
  `/guest/welcome`.
- Success responses use HTTP 303.
- Success responses set `Referrer-Policy: strict-origin` and
  `Cache-Control: no-store`.
- Success responses set `grant_id=<generated-id>` with `HttpOnly`,
  `SameSite=Strict`, and `Max-Age=3600`.
- Open-redirect protections remain owned by `RedirectValidator`.

## `GET /guest/welcome`

- Renders `guest/welcome.html` with HTTP 200.
- Applies the same route-level guest security headers as form rendering.
- No request, schema, or storage behavior changes are allowed.

## `GET /guest/error`

### Accepted query fields

| Query field | Required | Current use |
|-------------|----------|-------------|
| `message` | no | Guest-visible error text after sanitization |

### Rendering contract

- Missing or empty message renders `An error occurred. Please try again.`
- Messages longer than 500 characters are truncated to 500 characters plus
  `...`.
- Basic HTML tags are stripped before template rendering.
- Empty text after stripping falls back to the default message.
- The retry URL is root-path-aware `/guest/authorize`.
- The route renders `guest/error.html` with route-level security headers.

## Audit Contract

Characterization tests must pin actor, action, outcome, target type, target ID,
and metadata keys/values for at least:

- Success for voucher and booking grants.
- Rate-limited authorization attempts.
- MAC extraction failure.
- Invalid code format.
- Voucher VLAN denial, device-limit denial, and redemption failure.
- Booking not found, outside window, duplicate grant, integration unavailable,
  and VLAN denial.
- Controller authorization failure.

Timestamps may be normalized; stable metadata values must match exactly.
