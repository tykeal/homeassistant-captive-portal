SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Omada OpenAPI Migration

**Feature**: 013-omada-openapi-migration
**Date**: 2026-06-26

## Entities

### 1. OmadaConfig (Extended)

**Location**: `addon/src/captive_portal/models/omada_config.py`
**Type**: SQLModel singleton table (`id=1`)

| Field | Type | Default | Validation | Notes |
|-------|------|---------|------------|-------|
| `id` | `int` | `1` | Primary key | Existing singleton row |
| `controller_url` | `str` | `""` | http/https URL or empty | Existing |
| `username` | `str` | `""` | Non-empty when legacy needed | Existing legacy credential |
| `encrypted_password` | `str` | `""` | Fernet ciphertext or empty | Existing legacy secret |
| `site_name` | `str` | `"Default"` | Non-empty | Existing human-readable site |
| `controller_id` | `str` | `""` | Existing hex validation | Existing `omadacId`; may be discovered |
| `verify_ssl` | `bool` | `True` | Boolean | Existing, applies to both backends |
| `client_id` | `str` | `""` | Non-empty when set | New OpenAPI app credential |
| `encrypted_client_secret` | `str` | `""` | Fernet ciphertext or empty | New encrypted OpenAPI secret |
| `openapi_mode` | `str` | `"auto"` | `auto`/`openapi`/`legacy` | New backend selection control |

**Business rules**:

- Legacy credentials are complete when `controller_url`, `username`, and
  `encrypted_password` are non-empty.
- OpenAPI credentials are complete when `controller_url`, `client_id`, and
  `encrypted_client_secret` are non-empty.
- Partial OpenAPI credentials in `auto` mode do not block legacy fallback when
  legacy credentials are complete; they do produce a warning that identifies the
  missing field without exposing secret values.
- `client_secret` is a transient UI/config input name. The database persists
  only encrypted ciphertext in `encrypted_client_secret`.
- Backend-aware configured checks are mandatory: legacy completeness and
  OpenAPI completeness are separate predicates, and startup/settings guards use
  the factory selection rules rather than requiring legacy username/password for
  forced OpenAPI mode.

**DDL/migration note**: Add nullable/text columns for `client_id`,
`encrypted_client_secret`, and `openapi_mode` with a default of `auto`. Existing
rows must migrate without operator action and remain legacy-capable.

---

### 2. Runtime Omada Backend Selection

**Location**: `addon/src/captive_portal/config/omada_config.py` and
`controllers/tp_omada/adapter_factory.py`
**Type**: Runtime value stored on FastAPI `app.state`

| Attribute | Type | Description |
|-----------|------|-------------|
| `requested_mode` | `Literal["auto", "openapi", "legacy"]` | Validated operator mode |
| `openapi_credentials_present` | `bool` | Both `client_id` and decrypted `client_secret` are available |
| `legacy_credentials_present` | `bool` | Existing legacy username/password are available |
| `probe_success` | `bool | None` | OpenAPI token probe outcome when attempted |
| `selected_backend` | `Literal["openapi", "legacy"]` | Backend for this app run |
| `selection_reason` | `str` | Secret-safe log/operator reason |

**Business rules**:

- Selection happens at startup or explicit settings save/rebuild, not per
  operation.
- Once selected, the backend does not change after token refresh, site lookup,
  authorization, revocation, or status failures.
- `openapi_mode="openapi"` fails if credentials are missing or the token probe
  fails.
- `openapi_mode="legacy"` does not require an OpenAPI probe.
- `openapi_mode="auto"` falls back to legacy only when legacy credentials are
  complete.

---

### 3. OpenAPI Token State

**Location**: `controllers/tp_omada/openapi_client.py` or
`openapi_adapter.py`
**Type**: In-memory runtime state; not persisted; protected by an `asyncio.Lock`
when shared across request-scoped adapter instances

| Attribute | Type | Description |
|-----------|------|-------------|
| `access_token` | `str | None` | Current OpenAPI access token |
| `refresh_token` | `str | None` | Current refresh token, if returned |
| `expires_at_monotonic` | `float` | Monotonic deadline for proactive refresh |
| `refresh_margin_seconds` | `int` | Suggested margin: 300 seconds |

**Business rules**:

- Tokens are never written to logs, audit records, validation messages, or the
  database.
- Use `client_credentials` for the initial token and `refresh_token` when an
  unexpired refresh token exists.
- Refresh before expiry; on refresh failure, fail the current operation through
  existing controller-error semantics and do not switch to legacy.

---

### 4. OpenAPI Site Cache

**Location**: `controllers/tp_omada/openapi_adapter.py`
**Type**: In-memory runtime cache; not persisted

| Attribute | Type | Description |
|-----------|------|-------------|
| `omadac_id` | `str` | Controller ID used in OpenAPI paths |
| `site_name` | `str` | Configured human-readable site name |
| `site_id` | `str | None` | Discovered OpenAPI site ID |

**Business rules**:

- Discover `site_id` once using `GET /openapi/v1/{omadacId}/sites` and cache it
  for the add-on run.
- Match by `name == site_name`; fail with an actionable controller/config error
  if no site matches.
- Existing `controller_id` auto-discovery through `/api/info` remains available
  when the configured ID is empty.

---

### 5. AccessGrant (Existing)

**Location**: `addon/src/captive_portal/models/access_grant.py`
**Type**: SQLModel table, no OpenAPI schema change expected

| Field | Use in this feature |
|-------|---------------------|
| `mac` / `device_id` | Passed to selected adapter after existing MAC validation |
| `start_utc` / `end_utc` | Add-on source of truth for grant duration |
| `status` | PENDING, ACTIVE, EXPIRED, REVOKED, FAILED semantics preserved |
| `controller_grant_id` | Legacy may store controller result; OpenAPI may use MAC or auth record ID if available |
| `omada_gateway_mac`, `omada_ap_mac`, `omada_vid`, `omada_ssid_name`, `omada_radio_id` | Preserved for legacy; OpenAPI ignores these mode-specific values |

**State transitions affected**:

```text
PENDING ── selected adapter authorize succeeds ──> ACTIVE
PENDING ── selected adapter authorize fails ─────> FAILED
ACTIVE  ── admin revoke ─────────────────────────> REVOKED + selected revoke
ACTIVE  ── grant expiry processing ──────────────> EXPIRED + selected revoke
```

The OpenAPI migration must not make per-grant duration depend on a controller
request body. `end_utc` remains authoritative and expiry processing calls the
selected backend's revoke/unauth capability.

## Relationships

```text
OmadaConfig ──decrypts/builds──> Runtime Omada Backend Selection
       │                                  │
       │                                  ├── OmadaLegacyAdapter
       │                                  └── OmadaOpenApiAdapter
       │                                             │
       │                                             ├── Token State
       │                                             └── Site Cache
       │
AccessGrant ──authorize/revoke/status──> OmadaControllerAdapter Protocol
```
