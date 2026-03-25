SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Contract: HA Supervisor Addon Configuration

**Feature Branch**: `003-addon-structure-refactor`
**Date**: 2025-07-15

> This contract defines the interface between the captive-portal addon and
> the Home Assistant Supervisor. The Supervisor reads `config.yaml` and
> `build.yaml` to determine how to build, configure, and present the addon.

## 1. `config.yaml` — Addon Metadata Contract

The HA Supervisor expects a `config.yaml` (or `config.json`) at the root of the
addon directory. This file declares the addon's identity, capabilities, and
user-configurable options.

### Required Fields

| Field | Type | Constraint | Value |
|---|---|---|---|
| `name` | string | Non-empty | `"Captive Portal Guest Access"` |
| `version` | string | Semver-like | `"0.0.0-dev"` |
| `slug` | string | `[a-z0-9_]+` | `"captive_portal_guest_access"` |
| `description` | string | Non-empty | *(project description)* |
| `arch` | list[string] | Valid HA architectures | `[amd64, aarch64]` |

### Capability Flags

| Field | Type | Effect |
|---|---|---|
| `startup` | string | Determines startup ordering; `"services"` starts after core services |
| `init` | bool | `false` = use s6-overlay from base image (standard pattern) |
| `panel_admin` | bool | `true` = show a link in the HA admin sidebar |
| `homeassistant_api` | bool | `true` = addon can call HA REST API |
| `ingress` | bool | `false` = no ingress proxy; direct port access |

### Network Contract

| Field | Type | Value | Notes |
|---|---|---|---|
| `webui` | string | `"http://[HOST]:[PORT:8080]"` | HA substitutes host and port |
| `ports` | map | `{"8080/tcp": 8080}` | Host port ↔ container port |
| `ports_description` | map | `{"8080/tcp": "Web admin & portal"}` | UI label |

### User Options Schema

| Option | Schema Type | Description |
|---|---|---|
| `log_level` | `list(trace\|debug\|info\|notice\|warning\|error\|fatal)?` | Optional; defaults to `info` |
| `session_idle_timeout` | `int(1,)?` | Optional; minutes before idle session expires |
| `session_max_duration` | `int(1,)?` | Optional; hours before session force-expires |

## 2. `build.yaml` — Build Configuration Contract

The HA Supervisor reads `build.yaml` to determine the base Docker image for
each supported architecture.

| Architecture | Base Image |
|---|---|
| `amd64` | `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21` |
| `aarch64` | `ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21` |

### Contract Rules

- Every architecture listed in `config.yaml:arch` MUST have a corresponding
  entry in `build.yaml:build_from`.
- The `Dockerfile` MUST use `ARG BUILD_FROM` and `FROM ${BUILD_FROM}` to
  accept the Supervisor's image selection.

## 3. Dockerfile — Build Context Contract

The HA Supervisor builds the addon by running `docker build` with the addon
directory as the build context.

### Invariants

- The build context is exactly the `addon/` directory contents.
- Files outside `addon/` are NOT available during the build.
- The `Dockerfile` MUST be at the root of the build context (`addon/Dockerfile`).
- All COPY sources MUST be relative paths within the build context.

### Build Outputs

| Artifact | Location in Container | Purpose |
|---|---|---|
| Python venv | `/app/.venv/` | Isolated runtime dependencies |
| Application code | `/app/.venv/lib/python3.*/site-packages/captive_portal/` | Installed package |
| s6 service scripts | `/etc/s6-overlay/s6-rc.d/` | Process supervision |

### Runtime Contract

- The container exposes port **8080**.
- The application is started by s6-overlay via the `captive-portal` longrun service.
- The service run script invokes `uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080`.
- If the process exits non-zero, s6-overlay restarts it automatically (longrun behavior).
