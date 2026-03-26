SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Dual-Port Networking

**Feature**: 004-dual-port-networking
**Date**: 2025-07-15

## Overview

This feature introduces no new database entities.  The data model impact is
limited to:

1. A new **route policy** (code-level, not persisted) that governs which routes
   are available on which listener.
2. New **configuration fields** in `AppSettings` for guest listener settings.
3. A new **FastAPI app factory** that constructs a guest-only application.

---

## Entity: AppSettings (updated)

**Module**: `addon/src/captive_portal/config/settings.py`
**Type**: Pydantic `BaseModel` (not a database model)

| Field | Type | Default | Source (Addon Option) | Source (Env Var) | Description |
|-------|------|---------|----------------------|------------------|-------------|
| `log_level` | `str` | `"info"` | `log_level` | `CP_LOG_LEVEL` | *(existing)* |
| `db_path` | `str` | `"/data/captive_portal.db"` | — | `CP_DB_PATH` | *(existing)* |
| `session_idle_minutes` | `int` | `30` | `session_idle_timeout` | `CP_SESSION_IDLE_TIMEOUT` | *(existing)* |
| `session_max_hours` | `int` | `8` | `session_max_duration` | `CP_SESSION_MAX_DURATION` | *(existing)* |
| **`guest_external_url`** | **`str`** | **`""`** | **`guest_external_url`** | **`CP_GUEST_EXTERNAL_URL`** | **External URL for guest portal redirects (e.g., `http://192.168.1.100:8099`). Empty = use request-relative paths.** |

**Validation rules for `guest_external_url`**:

- Must be a string (may be empty).
- If non-empty, must start with `http://` or `https://`.
- Must not end with a trailing `/`.
- Invalid values are logged as warnings and fall through to the default (empty).

---

## Entity: Route Policy (new, code-level)

The route policy is not a database entity — it is the architectural decision of
which `APIRouter` instances are mounted in each FastAPI app.

### Ingress App (`create_app()` — existing, unchanged)

Mounts the following routers.  This is the backward-compatible behavior.

| Router | Prefix | Category |
|--------|--------|----------|
| `admin_accounts.router` | `/api/admin/accounts` | Admin |
| `admin_auth.router` | `/api/admin/auth` | Admin |
| `audit_config.router` | `/api/audit` | Admin |
| `docs.router` | `/admin/docs`, `/admin/redoc` | Admin |
| `grants.router` | `/api/grants` | Admin |
| `portal_config.router` | `/api/portal` | Admin |
| `portal_settings_ui.router` | `/admin/portal-settings` | Admin |
| `vouchers.router` | `/api/vouchers` | Admin |
| `integrations_ui.router` | `/admin/integrations` | Admin |
| `captive_detect.router` | `/generate_204`, etc. | Guest/Detection |
| `guest_portal.router` | `/guest` | Guest |
| `health.router` | `/api` | System |
| root redirect (`/`) | `/` → `/admin/portal-settings/` | Admin |

### Guest App (`create_guest_app()` — new)

Mounts **only** guest, captive-detection, and health routers.

| Router | Prefix | Category |
|--------|--------|----------|
| `captive_detect.router` | `/generate_204`, etc. | Guest/Detection |
| `guest_portal.router` | `/guest` | Guest |
| `booking_authorize.router` | `/api/guest` | Guest |
| `health.router` | `/api` | System |
| root redirect (`/`) | `/` → `/guest/authorize` | Guest |

**Routers explicitly excluded from guest app**:

- `admin_accounts.router`
- `admin_auth.router`
- `audit_config.router`
- `docs.router`
- `grants.router`
- `portal_config.router`
- `portal_settings_ui.router`
- `vouchers.router`
- `integrations_ui.router`

These routers are never imported and never registered in the guest app factory.
Any HTTP request to their paths on the guest port returns a 404 (FastAPI's
default "Not Found" response), not a 401/403 authentication error.

---

## Entity: Guest FastAPI App (new)

**Module**: `addon/src/captive_portal/guest_app.py` (new file)

```
create_guest_app(settings: AppSettings | None = None) -> FastAPI
```

**Lifespan**:

- **Startup**: Same database initialization as `create_app()` — calls
  `create_db_engine()` and `init_db()`.  Both apps share the same global engine
  singleton from `persistence/database.py`.
- **Shutdown**: Calls `dispose_engine()`.

**Middleware stack** (ordered outermost → innermost):

1. `SecurityHeadersMiddleware` — with stricter CSP (no `frame-ancestors 'self'`,
   use `frame-ancestors 'none'` since the guest portal is not framed).

**No `SessionMiddleware`** — guest routes do not use admin sessions.

**Static files**: Mounts `/static/themes` (same theme directory) so guest
templates render correctly.

**Root redirect**: `GET /` → `/guest/authorize` (not `/admin/portal-settings/`).

---

## Entity: s6-overlay Service — captive-portal-guest (new)

**Location**: `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/`

| File | Content |
|------|---------|
| `type` | `longrun` |
| `run` | Bash script: reads `guest_external_url` from addon options via bashio, exports `CP_GUEST_EXTERNAL_URL`, then `exec python -m uvicorn captive_portal.guest_app:create_guest_app --factory --host 0.0.0.0 --port 8099` |
| `finish` | Bash script: logs non-zero/non-256 exit codes (same pattern as existing finish script) |
| `dependencies.d/` | Empty directory (no inter-service dependencies) |

**Registration**: `addon/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/captive-portal-guest`
(empty file).

---

## Entity: Addon Configuration (updated)

**File**: `addon/config.yaml`

### Ports (updated)

```yaml
ports:
  "8080/tcp": null        # Ingress — not exposed on host
  "8099/tcp": 8099        # Guest portal — default host port 8099
ports_description:
  "8080/tcp": Web interface (not needed with Ingress)
  "8099/tcp": Guest captive portal (configure WiFi controller to redirect here)
```

### Schema (updated)

```yaml
schema:
  log_level: "list(trace|debug|info|notice|warning|error|fatal)?"
  session_idle_timeout: "int(1,)?"
  session_max_duration: "int(1,)?"
  guest_external_url: "url?"
```

The `url?` schema type validates that the input is a valid URL (or empty).

---

## State Transitions

No new state machines.  Existing `AccessGrant` and `Voucher` state transitions
remain unchanged.  Guest authorization flow on both listeners follows the same
path:

```
Guest connects → Captive detection redirect → /guest/authorize (form) →
  POST booking/voucher code → Validate → Create grant → /guest/success
```

The only difference is the network path:

- **Ingress path**: HA proxy → port 8080 → `create_app()` → root_path rewriting
- **Guest path**: Direct → port 8099 → `create_guest_app()` → no root_path

---

## Relationships

```
┌─────────────────────┐     ┌─────────────────────┐
│  s6: captive-portal │     │ s6: captive-portal-  │
│  (port 8080)        │     │     guest (port 8099) │
│                     │     │                       │
│  create_app()       │     │  create_guest_app()   │
│  ┌───────────────┐  │     │  ┌─────────────────┐  │
│  │ Admin routes  │  │     │  │ Guest routes    │  │
│  │ Guest routes  │  │     │  │ Captive detect  │  │
│  │ Captive detect│  │     │  │ Health          │  │
│  │ Health        │  │     │  └─────────────────┘  │
│  │ Docs          │  │     │                       │
│  └───────────────┘  │     │  SecurityHeaders only  │
│                     │     │  (no SessionMiddleware) │
│  SecurityHeaders    │     │                       │
│  SessionMiddleware  │     └───────┬───────────────┘
│                     │             │
└───────┬─────────────┘             │
        │                           │
        └───────────┬───────────────┘
                    │
            ┌───────▼───────┐
            │  SQLite DB    │
            │  (shared)     │
            └───────────────┘
```
