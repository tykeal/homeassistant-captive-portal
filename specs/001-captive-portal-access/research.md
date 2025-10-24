SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Phase 0 Research

## TP-Omada External Portal API Summary
Source: TP-Link FAQ 3231 (External Portal Configuration): https://www.tp-link.com/us/support/faq/3231/. The controller redirects guest clients to the external portal with query parameters; the portal responds by calling controller endpoints.

### Auth Flow (High-Level)
Derived from FAQ sequence (Steps 1-13) emphasizing ControllerID + CSRF token flow for Controller >=5.0.15.
1. Guest connects to SSID; controller intercepts and redirects to external portal.
2. External portal presents login/voucher form and on submit calls Controller Authorize endpoint.
3. Controller enables client traffic and periodically (or on portal ping) validates the session.
4. Revoke (logout or expiry) triggers Controller Revoke endpoint.

### Redirect / Query Parameters (Controller/EAP/Gateway -> Portal)
Includes Controller v5 additions: controllerId now implicit in subsequent API paths; time units microseconds.
| Param | Description |
|-------|-------------|
| client_mac | Client device MAC (CLIENT_MAC) |
| ap_mac | Access point MAC (AP_MAC, only for EAP path) |
| ssid | SSID name |
| radio_id | Radio identifier (e.g., 0/1) |
| vlan | VLAN ID (VID, only for Gateway path) |
| origin_url | Originally requested URL |
| site | Controller site identifier (SITE_NAME) |

### Controller Login & CSRF (New in v5.x)
Hotspot operator login: POST https://<controller>:<port>/<controller_id>/api/v2/hotspot/login
Body: {"name":"OPERATOR_USERNAME","password":"OPERATOR_PASSWORD"}
Store cookie (TPEAP_SESSIONID or TPOMADA_SESSIONID >=5.11) and result.token as CSRF header `Csrf-Token`.

### Portal -> Controller Authorize (Sample)
POST http://<controller-host>:<port>/extportal/auth (path name may vary)
```
{
  "client_mac": "AA:BB:CC:DD:EE:FF",
  "voucher_code": "ABCD1234",
  "duration_minutes": 240,
  "up_kbps": 0,
  "down_kbps": 0,
  "remark": "voucher redeem"
}
```
Controller Response (example):
```
{ "errorCode": 0, "success": true }
```

### Authorization Payload (Differences EAP vs Gateway)
EAP requires: clientMac, apMac, ssidName, radioId, site, time, authType=4
Gateway requires: clientMac, gatewayMac, vid, site, time, authType=4
`time` is absolute expiration timestamp (microseconds since epoch) not duration.

### Revoke (Logout)
POST /extportal/revoke
```
{
  "client_mac": "AA:BB:CC:DD:EE:FF",
  "reason": "manual_logout"
}
```

### Requirements (From FAQ)
1. Allow self-signed cert OR upload trusted cert to Controller.
2. Persist session cookie (TPEAP_SESSIONID / TPOMADA_SESSIONID) across login and auth request.
3. Include Csrf-Token header on authorize call.

### Session / Heartbeat (Optional)
POST /extportal/session
```
{ "client_mac": "AA:BB:CC:DD:EE:FF" }
```
Response may include remaining time; we can use this to reconcile state for disconnect enforcement tests.

### Implementation Notes / Decisions
- Controller URL, Controller ID, hotspot operator credentials stored in secure config (Phase 1 model fields).
- HTTP errors & non-zero errorCode mapped to internal retry/backoff (Phase 3 tests T0300); treat missing/expired CSRF token as forced re-login.
- Voucher code normalization: uppercase A-Z0-9, length 8–12 (decision pending Phase 1); convert to expiration microsecond timestamp for `time`.

## Home Assistant REST API (Entity Discovery)
We will discover and map "Rental Control" entities to contextualize access grants (e.g., which rental the guest belongs to).

### Authentication
Use a stored long-lived access token.
Header:
```
Authorization: Bearer <HA_TOKEN>
Content-Type: application/json
```

### List All States
GET http://<home-assistant>/api/states
Response: array of entity objects:
```
{
  "entity_id": "sensor.rental_unit_101_status",
  "state": "occupied",
  "attributes": {"unit": "101", "guest_name": "Smith", "checkout": "2025-10-28"},
  "last_changed": "2025-10-24T12:00:00+00:00"
}
```
We will filter by a configurable prefix/domain pattern (e.g., `sensor.rental_`). Mapping configuration stored in entity_mapping model (Phase 1) referencing chosen entities.

### Targeted Entity Lookup
GET /api/states/<entity_id>
Use for incremental refresh or validation when applying grants.

### Decisions / Open Points for Phase 1
1. Voucher Code Policy: charset A-Z0-9, default length 10 (configurable?).
2. Grant Expiration Precision: minute-level vs second-level (propose minute-level to match vouchers).
3. Password Hashing: bcrypt via passlib (cost factor 12) for admin accounts.
4. Audit Log Correlation ID: UUIDv7 string stored per request; generated middleware (Phase 2) but field required in model Phase 1.
5. Entity Mapping Storage: store selected entity_ids and optional attribute keys to extract (guest_name, checkout).
6. Admin Username Uniqueness: case-insensitive uniqueness enforced at DB level (SQLite COLLATE NOCASE).
7. Max Voucher Duration: configurable (default 1440 minutes) validated in model.
8. Omada Retry Policy: exponential backoff (base 0.5s, max 8s, 5 attempts) parameters to be constants.
9. Logging Format: structured JSON by default with logger name + correlation_id; plain text fallback if env VAR CP_JSON_LOG=0.
10. Config Loading Source: environment variables precedence > pyproject defaults > .env (if added later).

## Phase 0 Review (Task T0008)
Re-evaluated spec analysis: no blockers for Phase 1. Decisions required are enumerated above (1–10). Any undecided items must be finalized before implementing models/tests (T0100+). No additional remediation tasks identified at this time.
