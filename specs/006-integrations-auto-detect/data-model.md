SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Integrations Auto-Detection

**Feature**: 006-integrations-auto-detect | **Date**: 2025-07-14

This feature does not introduce new database entities. It adds a transient (non-persisted) view model for discovered integrations and modifies how the existing `HAIntegrationConfig.integration_id` field is populated (from pick-list selection rather than manual text entry). The schema of `HAIntegrationConfig` itself is unchanged.

## Existing Entities (no schema changes)

### HAIntegrationConfig

**Table**: `ha_integration_config` | **Module**: `captive_portal.models.ha_integration_config`

| Field | Type | UI Role in This Feature | Notes |
|-------|------|------------------------|-------|
| `id` | UUID (PK) | Hidden; used in edit/delete URLs | Unchanged |
| `integration_id` | str(128), unique, indexed | **Populated from pick-list selection** (was free-text input) | Entity ID from HA, e.g., `calendar.rental_control_beach_house` |
| `identifier_attr` | IdentifierAttr enum | Dropdown (slot_code/slot_name/last_four) | Unchanged |
| `checkout_grace_minutes` | int (0–30) | Number input | Unchanged |
| `last_sync_utc` | datetime, nullable | Displayed in configured list | Read-only |
| `stale_count` | int (≥0) | Displayed in configured list | Read-only |

**Validation Rules** (unchanged):
- `integration_id`: required, 1–128 chars, unique across table
- `identifier_attr`: one of `slot_code`, `slot_name`, `last_four`
- `checkout_grace_minutes`: 0–30, default 15

**Key Change**: The `integration_id` field is now populated by selecting from the auto-detected pick-list rather than typing manually. The stored value is the full HA entity ID (e.g., `calendar.rental_control_beach_house`). When auto-detection is unavailable, the free-text input remains as fallback, accepting any string that matches the existing validation rules.

---

## New View Models (transient — not persisted)

### DiscoveredIntegration

**Purpose**: Represents a Rental Control integration discovered from the Home Assistant API. Used only during the selection flow; never persisted to the database.
**Source**: Constructed by `HADiscoveryService.discover()` from HA API `GET /api/states` response.
**Module**: `captive_portal.integrations.ha_discovery_service`

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `entity_id` | str | `entity["entity_id"]` | Full HA entity ID, e.g., `calendar.rental_control_beach_house`. Used as the `integration_id` value when selected. |
| `friendly_name` | str | `entity["attributes"]["friendly_name"]` | Human-readable label for the pick-list, e.g., "Rental Control Beach House" |
| `state` | str | `entity["state"]` | Current state: `"on"` (active booking), `"off"` (idle), `"unavailable"` |
| `state_display` | str | Derived | Human-readable: "Active booking", "No active bookings", "Unavailable" |
| `event_summary` | str \| None | `entity["attributes"].get("message")` | Current event summary (guest name + code), or None if no active event |
| `event_start` | str \| None | `entity["attributes"].get("start_time")` | Current/next event start datetime string, or None |
| `event_end` | str \| None | `entity["attributes"].get("end_time")` | Current/next event end datetime string, or None |
| `already_configured` | bool | Cross-referenced with DB | True if `entity_id` matches an existing `HAIntegrationConfig.integration_id` |

**Derived Fields**:
```
state_display:
  if state == "on"          → "Active booking"
  if state == "off"         → "No active bookings"
  if state == "unavailable" → "Unavailable"
  else                      → state (pass-through)
```

**Validation Rules** (for data integrity, not user input):
- `entity_id`: must start with `calendar.rental_control_`
- `friendly_name`: non-empty string; fallback to `entity_id` if attribute missing
- `state`: any string (passed through from HA)
- `event_summary`, `event_start`, `event_end`: nullable, raw strings from HA

**Lifecycle**:
1. Created by `HADiscoveryService.discover()` during page load or refresh
2. Annotated with `already_configured` by the UI route handler
3. Passed to Jinja2 template as list
4. Discarded after response is rendered (no caching)

---

### DiscoveryResult

**Purpose**: Wrapper for the discovery outcome, encapsulating both the list of discovered integrations and any error state.
**Module**: `captive_portal.integrations.ha_discovery_service`

| Field | Type | Description |
|-------|------|-------------|
| `available` | bool | True if discovery succeeded (even with zero results) |
| `integrations` | list[DiscoveredIntegration] | Discovered integrations (empty if unavailable) |
| `error_message` | str \| None | User-facing error message if discovery failed |
| `error_category` | str \| None | Machine-readable category: `"timeout"`, `"auth"`, `"connection"`, `"server_error"`, `"unknown"` |

---

## Relationships Diagram

```
                          ┌─────────────────────────┐
                          │    HA REST API           │
                          │  GET /api/states         │
                          └────────────┬────────────┘
                                       │
                                       │ HTTP Response (all entities)
                                       ▼
                          ┌─────────────────────────┐
                          │   HAClient               │
                          │   .get_all_states()      │
                          └────────────┬────────────┘
                                       │
                                       │ list[dict]
                                       ▼
                          ┌─────────────────────────┐
                          │  HADiscoveryService      │
                          │  .discover()             │
                          │                          │
                          │  Filters for             │
                          │  calendar.rental_control_ │
                          └────────────┬────────────┘
                                       │
                                       │ DiscoveryResult
                                       │   (list[DiscoveredIntegration])
                                       ▼
                 ┌──────────────────────────────────────┐
                 │  integrations_ui.py route handler     │
                 │                                      │
                 │  Cross-references with DB:            │
                 │  ┌──────────────────────┐            │
                 │  │  HAIntegrationConfig  │            │
                 │  │  (configured list)    │            │
                 │  └──────────────────────┘            │
                 │                                      │
                 │  Sets already_configured flag         │
                 └──────────────────┬───────────────────┘
                                    │
                                    │ Template context
                                    ▼
                 ┌──────────────────────────────────────┐
                 │  integrations.html (Jinja2)          │
                 │                                      │
                 │  IF discovery_result.available:       │
                 │    Pick-list dropdown with            │
                 │    DiscoveredIntegration items        │
                 │    + entity state details             │
                 │    + "Already added" badges           │
                 │  ELSE:                               │
                 │    Manual text input (fallback)       │
                 │    + Error banner using               │
                 │      discovery_result.error_message   │
                 └──────────────────────────────────────┘
```

No new database tables, foreign keys, or relationships are added. All new data structures are transient Python dataclasses/Pydantic models.
