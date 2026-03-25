SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Addon Application Wiring

This feature introduces one new configuration model (`AppSettings`) and
modifies the application factory to accept it. No new database models are
added — all 8 existing SQLModel tables are unchanged.

## New: AppSettings (Configuration Model)

**Module**: `src/captive_portal/config/settings.py`
**Type**: pydantic `BaseModel` (not a database model)
**Purpose**: Single source of truth for application configuration, merging
addon options, environment variables, and built-in defaults.

### Fields

| Field | Type | Default | Env Var | Addon Option | Validation |
|-------|------|---------|---------|--------------|------------|
| `log_level` | `str` | `"info"` | `CP_LOG_LEVEL` | `log_level` | Must be one of: trace, debug, info, notice, warning, error, fatal |
| `db_path` | `str` | `"/data/captive_portal.db"` | `CP_DB_PATH` | _(not exposed)_ | Must be a writable filesystem path |
| `session_idle_minutes` | `int` | `30` | `CP_SESSION_IDLE_TIMEOUT` | `session_idle_timeout` | ≥1 |
| `session_max_hours` | `int` | `8` | `CP_SESSION_MAX_DURATION` | `session_max_duration` | ≥1 |

### Precedence Rules (FR-009)

For each field independently:

1. **Addon option** (from `/data/options.json`): Used if present AND valid.
2. **Environment variable** (with `CP_` prefix): Used if addon option is
   missing or invalid, AND env var is present AND valid.
3. **Built-in default**: Used if both addon option and env var are missing
   or invalid.

If an addon option value fails validation (wrong type, out of range), a
warning is logged describing the invalid value and the effective value used.
Only that specific field falls through — other valid addon options are kept.

### Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `load` | `@classmethod load(options_path: str = "/data/options.json") -> AppSettings` | Load settings with full precedence chain |
| `to_session_config` | `() -> SessionConfig` | Convert session fields to existing `SessionConfig` |
| `to_log_config` | `() -> dict[str, Any]` | Return logging configuration dict |
| `log_effective` | `(logger: logging.Logger) -> None` | Log all effective settings at INFO level (no secrets) |

### Example

```python
settings = AppSettings.load()
# Addon options.json has: {"log_level": "debug", "session_idle_timeout": -5}
# Env var CP_SESSION_IDLE_TIMEOUT=15 is set
# Result:
#   log_level = "debug"          (from addon option — valid)
#   session_idle_minutes = 15    (addon option invalid → env var)
#   session_max_hours = 8        (no addon option, no env var → default)
#   db_path = "/data/captive_portal.db"  (not in addon options → default)
# Warning logged: "Invalid addon option 'session_idle_timeout': -5
#   (must be ≥1). Using environment variable value: 15"
```

## Modified: Application Factory (`create_app`)

**Current signature**: `create_app() -> FastAPI`
**New signature**: `create_app(settings: AppSettings | None = None) -> FastAPI`

When `settings` is `None`, the factory calls `AppSettings.load()` to load
from addon options / env vars / defaults. This preserves backward
compatibility with existing tests that call `create_app()` without arguments.

### Startup Behavior Changes

1. Load `AppSettings` (if not provided).
2. Configure Python logging from `settings.to_log_config()`.
3. Log effective configuration via `settings.log_effective(logger)`.
4. Create database engine: `create_db_engine(f"sqlite:///{settings.db_path}")`.
5. Initialize database tables: `init_db(engine)`.
6. Create `SessionConfig` from `settings.to_session_config()`.
7. Register middleware and routes (unchanged).
8. Mount static files for themes directory.
9. Register lifespan handler for graceful shutdown.

### Shutdown Behavior

On application shutdown (SIGTERM → uvicorn graceful stop):

1. `dispose_engine()` called — closes all SQLAlchemy connection pool connections.
2. Uvicorn completes in-flight requests (up to 10s timeout).
3. Process exits cleanly.

## Modified: Database Module

**New function**: `dispose_engine() -> None`

Calls `_engine.dispose()` on the module-level engine to close all pooled
connections. Called during application shutdown via the lifespan handler.

## Existing Models (Unchanged)

The following 8 database models are created automatically by `init_db()` on
first startup. No schema changes are made by this feature:

| Model | Table | Purpose |
|-------|-------|---------|
| `AdminUser` | `adminuser` | Admin accounts (UUID PK, Argon2 hash) |
| `AdminSession` | `admin_session` | Admin session data |
| `AccessGrant` | `accessgrant` | WiFi access grants (voucher/booking) |
| `Voucher` | `voucher` | Redeemable access codes |
| `AuditLog` | `auditlog` | Immutable audit trail |
| `PortalConfig` | `portalconfig` | Guest portal settings (singleton) |
| `HAIntegrationConfig` | `haintegrationconfig` | HA Rental Control mapping |
| `RentalControlEvent` | `rentalcontrolevent` | Cached booking events |

## Entity Relationship Summary

```
AppSettings (new, in-memory)
    ├── produces → SessionConfig (existing, in-memory)
    ├── configures → create_db_engine() (existing)
    └── configures → Python logging (stdlib)

create_app() (modified)
    ├── reads → AppSettings
    ├── calls → create_db_engine() + init_db()
    ├── mounts → StaticFiles (new)
    ├── registers → lifespan handler (new)
    └── creates → FastAPI app with middleware + routes (existing)
```
