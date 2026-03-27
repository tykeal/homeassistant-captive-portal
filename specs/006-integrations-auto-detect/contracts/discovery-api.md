SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Discovery API Contract

**Feature**: 006-integrations-auto-detect | **Date**: 2025-07-14

This document defines the contract for the new discovery JSON endpoint and the modifications to the existing integrations UI route. All routes require admin authentication unless otherwise noted.

---

## GET /api/integrations/discover

**Purpose**: Discover available Rental Control integrations from Home Assistant (FR-001, FR-009).
**Authentication**: Required (via `require_admin` dependency)
**Response**: `200 OK` — `application/json`

### Response Schema (Success)

```json
{
  "available": true,
  "integrations": [
    {
      "entity_id": "calendar.rental_control_beach_house",
      "friendly_name": "Rental Control Beach House",
      "state": "on",
      "state_display": "Active booking",
      "event_summary": "John Doe - Booking 1234",
      "event_start": "2025-07-10 14:00:00",
      "event_end": "2025-07-17 11:00:00",
      "already_configured": false
    },
    {
      "entity_id": "calendar.rental_control_unit_3a",
      "friendly_name": "Rental Control Unit 3A",
      "state": "off",
      "state_display": "No active bookings",
      "event_summary": null,
      "event_start": null,
      "event_end": null,
      "already_configured": true
    }
  ],
  "error_message": null,
  "error_category": null
}
```

### Response Schema (HA API Unavailable)

```json
{
  "available": false,
  "integrations": [],
  "error_message": "Auto-detection timed out. You can enter the integration ID manually.",
  "error_category": "timeout"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `available` | bool | `true` if HA API was reachable and responded successfully |
| `integrations` | array | List of discovered integration objects (empty if unavailable) |
| `integrations[].entity_id` | string | Full HA entity ID (e.g., `calendar.rental_control_beach_house`) |
| `integrations[].friendly_name` | string | Human-readable name from HA attributes |
| `integrations[].state` | string | Raw HA state value: `"on"`, `"off"`, `"unavailable"` |
| `integrations[].state_display` | string | Human-readable state: "Active booking", "No active bookings", "Unavailable" |
| `integrations[].event_summary` | string \| null | Current event summary (guest name + code) |
| `integrations[].event_start` | string \| null | Current/next event start datetime |
| `integrations[].event_end` | string \| null | Current/next event end datetime |
| `integrations[].already_configured` | bool | `true` if entity_id matches an existing `HAIntegrationConfig.integration_id` |
| `error_message` | string \| null | User-safe error message if discovery failed |
| `error_category` | string \| null | Machine-readable error category: `"timeout"`, `"auth"`, `"connection"`, `"server_error"`, `"unknown"` |

### Error Categories

| Category | HTTP Status (from HA) | Example |
|----------|----------------------|---------|
| `timeout` | N/A (request timed out) | HA is slow or unresponsive |
| `auth` | 401, 403 | Invalid or expired Supervisor token |
| `connection` | N/A (connection refused) | HA Supervisor not reachable |
| `server_error` | 500, 502, 503 | HA internal error |
| `unknown` | Any other | Unexpected exception |

Implementations of this endpoint MUST derive `error_category` from the underlying HTTP client error/response, not by collapsing all failures into a generic `Exception`. The discovery logic MUST either:

- inspect HTTP client exceptions directly (for example, `httpx.HTTPError` and its subclasses), or
- raise/handle a typed or custom exception that:
  - encodes a specific `error_category` from the table above, and
  - does **not** include request URLs, headers, bodies, or raw response content in its public message.

Generic `Exception` messages (or stringified HTTP exceptions) MUST NOT be exposed to callers or used verbatim as `error_message`. Only fixed, user-safe strings defined by this contract may be sent in responses.

### Security

- The response MUST NOT include the HA API token, internal URLs, or raw HTTP response bodies
- Error messages MUST be constrained to the categories above and MUST NOT contain raw exception texts (including `httpx.HTTPError` or generic `Exception` messages)
- Full error details (stack traces, raw responses, full exception objects/messages) MUST be logged server-side only and NEVER returned to the client

---

## GET /admin/integrations/ (Modified)

**Purpose**: Display integrations page with auto-detected pick-list (FR-002, FR-003, FR-004, FR-007).
**Authentication**: Required (redirect to `/admin/login` if unauthenticated)
**Response**: `200 OK` — `text/html`

### Behavior Change
The route handler now calls `HADiscoveryService.discover()` before rendering the template. The discovery result is passed to the template along with the existing configured integrations list.

### Template Context (Modified)

| Variable | Type | Description | New? |
|----------|------|-------------|------|
| `integrations` | list[HAIntegrationConfig] | Existing configured integrations | No |
| `integration` | HAIntegrationConfig \| None | Integration being edited (for edit form) | No |
| `csrf_token` | str | CSRF token | No |
| `discovery_result` | DiscoveryResult | Discovery outcome (available, integrations, error) | **Yes** |

### Template Rendering Logic

```
IF discovery_result.available AND len(discovery_result.integrations) > 0:
  Show pick-list dropdown populated with discovered integrations
  Each option shows: friendly_name + state_display + event_summary
  Options with already_configured=true are disabled + show "Already added" badge
  Include refresh button (triggers JS fetch to /api/integrations/discover)

ELIF discovery_result.available AND len(discovery_result.integrations) == 0:
  Show empty state message: "No Rental Control integrations found..."
  Show manual entry text input as fallback

ELSE (discovery_result.available == false):
  Show notification banner with discovery_result.error_message
  Show manual entry text input as fallback
```

### Timeout Behavior
The discovery call has a 10-second timeout. The server will wait up to 10 seconds for discovery to complete before rendering the page. If discovery times out, the page renders after the timeout with the manual fallback, and discovery data is omitted. The page is not blocked indefinitely beyond the configured timeout.

### Response Headers
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```
(Inherited from existing `SecurityHeadersMiddleware` for all `/admin/*` paths.)

---

## POST /admin/integrations/save (Modified)

**Purpose**: Save integration configuration from pick-list selection or manual entry.
**Authentication**: Required
**CSRF**: Required
**Content-Type**: `application/x-www-form-urlencoded`

### Form Fields (Modified)

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `csrf_token` | str | Yes | Hidden | CSRF protection token |
| `integration_id` | str | Yes | Pick-list `<select>` value OR manual text input | HA entity ID |
| `identifier_attr` | str | Yes | Dropdown | `slot_code`, `slot_name`, or `last_four` |
| `checkout_grace_minutes` | int | Yes | Number input | 0–30 |
| `id` | UUID \| None | No | Hidden | Existing config UUID (for updates) |

**Key Change**: The `integration_id` field value now comes from either:
1. The `<select>` dropdown (when auto-detection is available) — the `<option value="">` is set to the full entity ID
2. The `<input type="text">` field (when auto-detection is unavailable) — free-text entry, same as before

The server-side validation and storage logic in the POST handler is **unchanged**. The `integration_id` value is treated identically regardless of source.

---

## Cross-Cutting Behaviors

### Authentication Redirect
Same as all existing admin routes: unauthenticated `GET /admin/*` requests → `303 See Other` → `{root_path}/admin/login`.

### Ingress Root Path
All URLs in templates and redirects are prefixed with `request.scope.get("root_path", "")`.

### CSRF Pattern
All state-changing POST routes validate CSRF using the existing double-submit cookie pattern. The `GET /api/integrations/discover` endpoint is read-only and does not require CSRF.

### SPDX Headers
All new source files include:
```
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
```

### Content Security Policy
The new `admin-integrations.js` file is loaded via `<script src="{{ rp }}/static/themes/default/admin-integrations.js"></script>`, which complies with the existing `script-src 'self'` CSP policy. No inline scripts.
