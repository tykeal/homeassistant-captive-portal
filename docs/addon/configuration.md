<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Addon Configuration Reference

This document describes the configuration options available through the
Home Assistant addon configuration panel and the corresponding environment
variables for standalone deployment.

## Addon Configuration Options

These settings are configured in the Home Assistant addon configuration tab.
All options are optional — the addon starts with sensible defaults.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `log_level` | list | `info` | Application log verbosity. Options: trace, debug, info, notice, warning, error, fatal |
| `session_idle_timeout` | integer (≥1) | `30` | Minutes of inactivity before admin sessions expire |
| `session_max_duration` | integer (≥1) | `8` | Maximum hours an admin session remains active |

## Environment Variables

When running outside the addon container, configure via environment variables
with the `CP_` prefix:

| Variable | Default | Maps to |
|----------|---------|---------|
| `CP_LOG_LEVEL` | `info` | `log_level` addon option |
| `CP_DB_PATH` | `/data/captive_portal.db` | Database file path (not exposed as addon option) |
| `CP_SESSION_IDLE_TIMEOUT` | `30` | `session_idle_timeout` addon option |
| `CP_SESSION_MAX_DURATION` | `8` | `session_max_duration` addon option |

## Precedence Rules

For each setting independently, the following priority applies:

1. **Addon option** (from `/data/options.json`): Used if present and valid
2. **Environment variable** (with `CP_` prefix): Used if addon option is
   missing or invalid
3. **Built-in default**: Used if both addon option and env var are missing
   or invalid

If a specific addon option value is invalid (wrong type, out of range),
only that field falls through — other valid addon options are kept. A
warning is logged describing the invalid value and the effective value used.

## Log Level Mapping

Home Assistant addon log levels map to Python logging levels:

| HA Level | Python Level |
|----------|-------------|
| trace | DEBUG |
| debug | DEBUG |
| info | INFO |
| notice | INFO |
| warning | WARNING |
| error | ERROR |
| fatal | CRITICAL |

## Data Persistence

The addon stores its SQLite database at `/data/captive_portal.db`.
The `/data/` directory is a persistent volume managed by the HA Supervisor
— data survives addon restarts and upgrades.

## Example: Development Configuration

```bash
CP_LOG_LEVEL=debug CP_DB_PATH=./dev.db CP_SESSION_IDLE_TIMEOUT=60 \
  uv run uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080 --reload
```
