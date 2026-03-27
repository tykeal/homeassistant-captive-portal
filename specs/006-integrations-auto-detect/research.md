SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Integrations Auto-Detection

**Feature**: 006-integrations-auto-detect | **Date**: 2025-07-14

## R1: HA REST API Discovery Mechanism — Entity Enumeration

### Decision
Use `GET /api/states` on the Home Assistant REST API to retrieve all entity states, then filter client-side for entities matching the `calendar.rental_control_*` naming pattern. A new `get_all_states()` method on `HAClient` will return the full entity list, and `HADiscoveryService` will apply the filter and extract relevant attributes.

### Rationale
The HA REST API does not provide a built-in "list integrations" endpoint that returns integration-level metadata. However, Rental Control integrations expose calendar entities that follow a discoverable naming convention (`calendar.rental_control_<name>`). The `GET /api/states` endpoint returns all entity states in a single call, which is efficient for addons running inside the Supervisor network (local HTTP, no TLS overhead, sub-second latency). The client-side filter approach avoids depending on undocumented HA internals.

The `homeassistant_api: true` flag in `config.yaml` causes the Supervisor to inject a `SUPERVISOR_TOKEN` environment variable. The addon accesses the HA API at `http://supervisor/core/api` using this token as a Bearer header — exactly as the existing `HAClient` already does.

### Alternatives Considered
1. **Query individual entities by known pattern (e.g., `GET /api/states/calendar.rental_control_*`)**: Rejected — the HA REST API does not support wildcard entity queries. Each entity must be fetched individually, which requires knowing the entity IDs in advance (the exact problem we're solving).
2. **Use the HA WebSocket API (`/api/websocket`)**: Rejected — adds complexity (WebSocket state management, auth handshake) for a one-shot discovery call. The REST API is simpler and the existing `HAClient` already uses httpx for REST.
3. **Use the HA integration registry (`/api/config/config_entries/entry`)**: Rejected — returns config entries, not entity states. Would require a second call to get entity data. Also, the endpoint may require `auth_api: true` permissions not currently configured.
4. **Enumerate entities via `GET /api/services` or template API**: Rejected — services don't map to entities directly; template API adds unnecessary complexity.

### Entity Naming Pattern
Rental Control integrations create calendar entities following the pattern:
```
calendar.rental_control_<integration_name>
```
Where `<integration_name>` is derived from the HA config entry title (spaces replaced with underscores, lowercased). For example:
- Integration title "Beach House" → `calendar.rental_control_beach_house`
- Integration title "Unit 3A" → `calendar.rental_control_unit_3a`

The discovery service will filter entities where `entity_id` starts with `calendar.rental_control_`.

### HA API Response Structure
`GET /api/states` returns an array of entity state objects:
```json
[
  {
    "entity_id": "calendar.rental_control_beach_house",
    "state": "on",
    "attributes": {
      "friendly_name": "Rental Control Beach House",
      "message": "Guest Name - Booking 1234",
      "all_day": false,
      "start_time": "2025-07-10 14:00:00",
      "end_time": "2025-07-17 11:00:00",
      "description": "...",
      "offset_reached": false
    },
    "last_changed": "2025-07-10T14:00:00.123456+00:00",
    "last_updated": "2025-07-14T08:00:00.654321+00:00"
  }
]
```

Key observations:
- `state` is `"on"` when an active booking exists, `"off"` when idle
- `attributes.friendly_name` provides the human-readable label
- `attributes.message` contains the current event summary (guest name + code)
- `attributes.start_time` / `attributes.end_time` are the current/next event window
- Additional event-specific attributes may vary

---

## R2: Extracting Entity State Details — Active Booking Context

### Decision
For each discovered `calendar.rental_control_*` entity, extract and display:
1. **Friendly name**: From `attributes.friendly_name` (primary label)
2. **State**: `"on"` → "Active booking" / `"off"` → "No active bookings" / `"unavailable"` → "Unavailable"
3. **Current event summary**: From `attributes.message` when state is `"on"` (contains guest name and booking code)
4. **Next event dates**: From `attributes.start_time` and `attributes.end_time` when available
5. **Active booking indicator**: Derived from state (`"on"` = active, `"off"` = idle)

Active booking **count** is not directly available from the calendar entity state (HA exposes only the current/next event, not a numeric count of overlapping bookings). For this feature, we interpret "active booking count" in FR-004 as a binary value derived from the calendar state: `state == "on"` implies "at least one active booking" (count ≥ 1), and `state == "off"` implies "0 active bookings". The pick-list will therefore display "Active booking" or "No active bookings" as this binary indicator. FR-004 and its acceptance criteria will be updated so that any references to an "active booking count" or examples like "two active bookings" refer to this 0/≥1 representation rather than a precise numeric count per integration.

### Rationale
The calendar entity state in HA provides a snapshot of the current/next event. This is the same data the existing `HAPoller` uses for event processing. Extracting these fields gives admins enough context to identify the correct integration without leaving the page (User Story 2).

### Alternatives Considered
1. **Query each entity's event list via `GET /api/calendars/<entity_id>`**: Rejected — this HA endpoint returns upcoming calendar events, which would give a count. However, it requires a separate HTTP call per entity (N+1 problem with 20+ integrations), and the calendar API may not be available in all HA installations.
2. **Cross-reference with `RentalControlEvent` cache table**: Rejected — the cache contains events from already-configured integrations only; we need to show events for integrations *not yet* configured.

---

## R3: Timeout and Fallback Strategy

### Decision
Apply a **10-second timeout** on the `GET /api/states` call. If the call fails (timeout, connection refused, HTTP error, auth error), the UI route catches the exception and falls back to rendering the manual text entry field with a notification banner. The notification includes the failure category (timeout, authentication error, connection refused, HTTP error) without exposing sensitive details (tokens, internal URLs, raw response bodies).

### Rationale
SC-004 requires the manual fallback within 10 seconds. SC-005 requires the pick-list to populate within 5 seconds under normal conditions. The 10-second timeout gives a generous buffer for slow HA instances while meeting the fallback SLA.

The fallback approach is server-side: the UI route handler wraps the discovery call in a try/except. On failure, it sets `discovery_available=False` and `discovery_error="..."` in the template context. The Jinja2 template renders different HTML depending on this flag. This means the fallback works without JavaScript.

### Error Classification
| HA API Error | Notification Text | Log Level |
|---|---|---|
| `httpx.TimeoutException` | "Auto-detection timed out. You can enter the integration ID manually." | WARNING |
| `httpx.ConnectError` | "Cannot reach Home Assistant. You can enter the integration ID manually." | WARNING |
| `httpx.HTTPStatusError` (401/403) | "Auto-detection unavailable: authentication error. You can enter the integration ID manually." | ERROR |
| `httpx.HTTPStatusError` (5xx) | "Auto-detection unavailable: Home Assistant returned an error. You can enter the integration ID manually." | ERROR |
| Any other `Exception` | "Auto-detection unavailable. You can enter the integration ID manually." | ERROR |

Full error details (status code, URL, exception traceback) are logged server-side for troubleshooting, per FR-008.

### Alternatives Considered
1. **Client-side timeout via JavaScript fetch with AbortController**: Rejected — the primary UI must work without JS (server-rendered). JS-based timeout would be progressive enhancement only and wouldn't cover the non-JS case.
2. **Separate loading page with redirect**: Rejected — adds unnecessary complexity and a worse UX than a single page that shows a pick-list or falls back to manual entry.
3. **Background discovery with polling**: Rejected — over-engineering for a single API call. The HA API is local (supervisor network), so latency is minimal.

---

## R4: Integration Identity — Mapping Discovered Entities to `integration_id`

### Decision
The `integration_id` stored in `HAIntegrationConfig` will be the full entity ID from Home Assistant (e.g., `calendar.rental_control_beach_house`). When the admin selects an integration from the pick-list, the hidden form field is populated with this entity ID. This maintains consistency with the existing system where `HAClient.get_entity_state(entity_id)` is called during polling.

### Rationale
The existing `HAPoller` and `RentalControlService` use `integration_id` as the entity ID for `GET /api/states/{entity_id}`. If we stored a different identifier (e.g., config entry ID), we'd need to add a mapping layer. Using the entity ID directly ensures the auto-detected selection works with the existing polling infrastructure without changes.

The current manual entry already expects the entity ID (the placeholder text says "rental_control_1" which is a partial entity ID). The spec (FR-011) explicitly requires: "System MUST use the integration identifier discovered from Home Assistant as the stored `integration_id` value."

### Alternatives Considered
1. **Store the HA config entry ID instead**: Rejected — would require changes to `HAPoller` and `RentalControlService` to resolve config entry IDs to entity IDs. The entity ID is the natural key.
2. **Store a derived short name (strip `calendar.` prefix)**: Rejected — the existing system may already have `integration_id` values with or without the prefix. Consistency with the existing data and the HA API is more important.

---

## R5: Duplicate Prevention — Marking Already-Configured Integrations

### Decision
When the discovery service returns available integrations, the UI route cross-references them against the existing `HAIntegrationConfig` records in the database. Each discovered integration is annotated with a boolean `already_configured` flag and, if configured, the existing config's UUID. The Jinja2 template renders already-configured integrations with a "Already added" badge, a `disabled` attribute on the `<option>` element, and a visual distinction (muted color).

### Rationale
FR-006 requires: "System MUST visually indicate integrations that are already configured in the captive portal and prevent duplicate additions." The existing create endpoint (`POST /api/integrations`) already enforces uniqueness on `integration_id` (returns 409 Conflict), so the server-side guard exists. The UI-side marking provides a better UX by preventing the admin from attempting to add a duplicate in the first place.

### Implementation
In the UI route handler:
```python
configured_ids = {config.integration_id for config in configured_integrations}
for discovered in discovered_integrations:
    discovered.already_configured = discovered.entity_id in configured_ids
```

### Alternatives Considered
1. **Only rely on server-side 409 rejection**: Rejected — poor UX; admin would fill out the form, submit, and get an error. Better to prevent the attempt.
2. **Hide already-configured integrations from the pick-list entirely**: Rejected — the admin should see all integrations for orientation, especially when managing which ones are and aren't configured.

---

## R6: Refresh Control — Progressive Enhancement JavaScript

### Decision
Add a "Refresh" button next to the pick-list that triggers a JavaScript `fetch()` call to `GET /api/integrations/discover` (a new JSON API endpoint). The JS handler replaces the dropdown options with the updated list, shows a loading spinner during the request, and handles errors by displaying the notification banner. Without JavaScript, the admin reloads the full page (the pick-list is populated server-side on each page load).

### Rationale
User Story 4 requires an in-page refresh without full page reload. The project's CSP policy allows `script-src 'self'`, so external JS files are permitted. The existing project has progressive enhancement JS files (`admin-grants.js`, `admin-login.js`, `admin-portal-settings.js`) that follow this same pattern.

The `GET /api/integrations/discover` endpoint returns JSON, consistent with the existing `/api/*` JSON endpoints. The UI route continues to serve the server-rendered page (with discovery data) for the initial load, and the JS endpoint provides data for subsequent refreshes.

### Alternatives Considered
1. **Full page reload via `<meta http-equiv="refresh">` or link**: Rejected — spec explicitly requests in-page refresh (FR-009).
2. **Server-Sent Events (SSE) for live updates**: Rejected — over-engineering for a manual refresh action. SSE would be appropriate for real-time monitoring but not for a button-triggered re-query.
3. **Inline fetch in a `<script>` tag**: Rejected — violates CSP `script-src 'self'`; must use external JS file.

### Loading Indicator
During the fetch, the button text changes to "Refreshing..." with a CSS animation spinner. The dropdown is disabled during the fetch to prevent interaction. On completion, the dropdown is re-enabled with updated options.

---

## R7: Empty State — No Rental Control Integrations Found

### Decision
When the HA API is reachable but returns zero `calendar.rental_control_*` entities, the UI displays an empty state message: "No Rental Control integrations found in Home Assistant. Install a Rental Control integration in HA first, or enter an integration ID manually below." The manual entry fallback is shown alongside the empty state.

### Rationale
The edge case specification explicitly requires: "The system displays a helpful empty state message explaining that no Rental Control integrations were found and suggests the admin install one in Home Assistant first, while still offering the manual entry fallback."

### Alternatives Considered
1. **Show only the manual entry (hide the empty pick-list)**: Rejected — the admin should understand *why* the pick-list is empty (no integrations in HA) rather than thinking the feature is broken.
2. **Show an error notification**: Rejected — this is not an error condition; it's a normal state when HA has no Rental Control integrations.

---

## R8: HAClient Extension — `get_all_states()` Method

### Decision
Add a new method `get_all_states()` to the existing `HAClient` class that calls `GET /api/states` and returns the full list of entity state dictionaries. Apply a configurable timeout (default 10 s) separate from the existing client timeout (30 s used for polling). The discovery service will call this method and filter the results.

### Rationale
The existing `HAClient.get_entity_state(entity_id)` fetches a single entity. Discovery needs all entities to filter for the `calendar.rental_control_*` pattern. Adding a method to `HAClient` keeps the HA API communication centralized rather than creating a parallel HTTP client.

The discovery-specific timeout (10 s) is shorter than the general client timeout (30 s) because discovery is user-facing (admin waiting for page load) and must meet SC-004's 10-second fallback SLA.

### Alternatives Considered
1. **Create a separate `HADiscoveryClient`**: Rejected — duplicates HTTP client setup, authentication, and error handling. The existing `HAClient` is the right place.
2. **Use the existing `get_entity_state()` in a loop**: Rejected — requires knowing entity IDs in advance (the discovery problem itself) and generates N HTTP calls instead of one.

### Method Signature
```python
async def get_all_states(self, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Retrieve all entity states from Home Assistant.

    Args:
        timeout: Request timeout in seconds (default 10.0)

    Returns:
        List of entity state dictionaries

    Raises:
        httpx.TimeoutException: On request timeout
        httpx.HTTPStatusError: On HTTP error responses
        httpx.ConnectError: On connection failure
    """
```
