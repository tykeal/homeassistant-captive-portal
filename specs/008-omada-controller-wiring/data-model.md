SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Omada Controller Integration Wiring

**Feature**: 008-omada-controller-wiring
**Date**: 2025-07-11

## Entities

### 1. AppSettings (Extended)

**Location**: `addon/src/captive_portal/config/settings.py`
**Type**: Pydantic `BaseModel` (existing, extended with new fields)

| Field | Type | Default | Validation | Source |
|-------|------|---------|------------|--------|
| `omada_controller_url` | `str` | `""` | URL (http/https) or empty | addon → CP_OMADA_CONTROLLER_URL → default |
| `omada_username` | `str` | `""` | Non-empty string when set | addon → CP_OMADA_USERNAME → default |
| `omada_password` | `str` | `""` | Non-empty string when set | addon → CP_OMADA_PASSWORD → default |
| `omada_site_name` | `str` | `"Default"` | Non-empty string | addon → CP_OMADA_SITE_NAME → default |
| `omada_controller_id` | `str` | `""` | Non-empty string when set | addon → CP_OMADA_CONTROLLER_ID → default |
| `omada_verify_ssl` | `bool` | `True` | Boolean | addon → CP_OMADA_VERIFY_SSL → default |

**Business rules**:
- Omada is considered "configured" when `omada_controller_url` is non-empty
- `omada_password` MUST NOT appear in `log_effective()` output — logged as `"(set)"` or `"(not set)"`
- `omada_verify_ssl` supports `"true"/"false"/"1"/"0"` from env vars, native bool from addon JSON

**Relationships**: Settings are consumed by lifespan functions in `app.py` and `guest_app.py` to construct `OmadaClient` + `OmadaAdapter`.

---

### 2. AccessGrant (Existing — No Schema Changes)

**Location**: `addon/src/captive_portal/models/access_grant.py`
**Type**: SQLModel with `table=True`

The `controller_grant_id` field already exists on `AccessGrant`:

| Field | Type | Notes |
|-------|------|-------|
| `controller_grant_id` | `str | None` | Max 128 chars. Populated by authorize flow on success. |
| `status` | `GrantStatus` | PENDING → ACTIVE (on controller success) or FAILED (on controller error) |
| `mac` | `str` | Used for controller authorize/revoke calls |

**State transitions affected by this feature**:

```
PENDING ──(controller auth success)──→ ACTIVE
PENDING ──(controller auth failure)──→ FAILED
PENDING ──(no controller configured)──→ ACTIVE
ACTIVE ──(admin revoke + controller revoke)──→ REVOKED
ACTIVE ──(admin revoke, no controller)──→ REVOKED
```

**No DDL changes needed** — all required columns already exist.

---

### 3. OmadaClient (Existing — No Changes)

**Location**: `addon/src/captive_portal/controllers/tp_omada/base_client.py`
**Type**: Plain Python class with async context manager

| Attribute | Type | Set At | Notes |
|-----------|------|--------|-------|
| `base_url` | `str` | Construction | Controller URL (no trailing slash) |
| `controller_id` | `str` | Construction | Omada controller ID |
| `username` | `str` | Construction | Hotspot operator username |
| `password` | `str` | Construction | Hotspot operator password |
| `verify_ssl` | `bool` | Construction | SSL verification toggle |
| `timeout` | `float` | Construction | HTTP timeout (seconds) |
| `_client` | `httpx.AsyncClient | None` | `__aenter__` | Created lazily on context entry |
| `_csrf_token` | `str | None` | `_authenticate()` | Set during first auth |
| `_session_cookie` | `str | None` | `_authenticate()` | Set during first auth |

**Lifecycle**:
- Construction: zero I/O (stores config only)
- `__aenter__`: creates httpx client, authenticates, extracts CSRF token + session cookie
- `__aexit__`: closes httpx client
- `post_with_retry()`: retries with exponential backoff; requires active client

---

### 4. OmadaAdapter (Existing — No Changes)

**Location**: `addon/src/captive_portal/controllers/tp_omada/adapter.py`
**Type**: Plain Python class wrapping OmadaClient

| Attribute | Type | Notes |
|-----------|------|-------|
| `client` | `OmadaClient` | Injected at construction |
| `site_id` | `str` | Omada site identifier (default: "Default") |

**Key methods** (all async, all require client to be in active context):

| Method | Input | Output | Controller Endpoint |
|--------|-------|--------|-------------------|
| `authorize(mac, expires_at, upload_limit_kbps, download_limit_kbps)` | MAC + expiry + bandwidth | `{grant_id, status, mac}` | `POST /extportal/auth` |
| `revoke(mac, grant_id?)` | MAC | `{success, mac}` | `POST /extportal/revoke` |
| `update(mac, expires_at, grant_id?)` | MAC + new expiry | same as authorize | Re-authorizes via `/extportal/auth` |
| `get_status(mac)` | MAC | `{mac, authorized, remaining_seconds}` | `POST /extportal/session` |

---

### 5. Addon Configuration Schema (Extended)

**Location**: `addon/config.yaml`
**Type**: HA addon config schema YAML

New fields under `schema:`:

| Key | Schema Type | Notes |
|-----|-------------|-------|
| `omada_controller_url` | `url?` | Optional URL |
| `omada_username` | `str?` | Optional string |
| `omada_password` | `password?` | Optional password (masked in HA UI) |
| `omada_site_name` | `str?` | Optional string |
| `omada_controller_id` | `str?` | Optional string |
| `omada_verify_ssl` | `bool?` | Optional boolean (defaults true in app) |

---

### 6. app.state Extension (Runtime)

**Location**: `app.py` and `guest_app.py` lifespan functions
**Type**: FastAPI `State` object (dynamic attributes)

New state attributes set during lifespan:

| Attribute | Type | When Set | When `None` |
|-----------|------|----------|-------------|
| `app.state.omada_client` | `OmadaClient | None` | Startup (if configured) | No Omada URL |
| `app.state.omada_adapter` | `OmadaAdapter | None` | Startup (if configured) | No Omada URL |

**Shutdown behavior**: Since route handlers use `async with client:` per operation, no global shutdown cleanup is needed for the OmadaClient. The client's async context manager handles session cleanup after each operation. If a future optimization introduces persistent connections, add a public `is_open` property and corresponding shutdown logic.

## Entity Relationship Diagram

```
┌──────────────────┐      constructs      ┌─────────────────┐
│   AppSettings    │─────────────────────→│   OmadaClient   │
│  (6 Omada fields)│                      │  (base_client)  │
└──────────────────┘                      └────────┬────────┘
                                                   │ injected
                                                   ▼
                                          ┌─────────────────┐
                                          │  OmadaAdapter   │
                                          │  (adapter)      │
                                          └────────┬────────┘
                                                   │
                               ┌───────────────────┼────────────────────┐
                               │                   │                    │
                               ▼                   ▼                    ▼
                    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
                    │ guest_portal.py  │  │   grants.py      │  │ app.state        │
                    │ authorize()      │  │   revoke()       │  │ .omada_adapter   │
                    │ FR-010..013      │  │   FR-014..018    │  │ .omada_client    │
                    └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘
                             │                     │
                             ▼                     ▼
                    ┌──────────────────────────────────────────┐
                    │            AccessGrant                    │
                    │  .status: PENDING→ACTIVE/FAILED          │
                    │  .controller_grant_id: set on success    │
                    │  .mac: used for controller calls         │
                    └──────────────────────────────────────────┘
```
