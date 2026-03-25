SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Data Model: Addon Structure Refactor (003)

**Feature Branch**: `003-addon-structure-refactor`
**Date**: 2025-07-15

> This feature is a structural refactor — no application data models (database
> entities, runtime state) are created or modified. The "data model" for this
> feature describes the **file and directory layout** that constitutes the addon's
> build and runtime structure.

## 1. Directory Layout Model

### 1.1 Addon Build Context (`addon/`)

The `addon/` directory is the Docker build context used by HA Supervisor.
Every file required to build the container image MUST reside here.

```text
addon/
├── build.yaml            # Architecture → base image mapping
├── config.yaml           # HA addon metadata (YAML, replaces config.json)
├── Dockerfile            # Container build instructions
├── pyproject.toml        # Python package definition (hatchling backend)
├── uv.lock               # Frozen dependency lock file
├── README.md             # Addon-level README
├── rootfs/               # s6-overlay filesystem overlay
│   └── etc/s6-overlay/s6-rc.d/
│       ├── captive-portal/
│       │   ├── run       # Service start script (longrun)
│       │   ├── finish    # Service exit handler
│       │   └── type      # "longrun" marker
│       └── user/contents.d/
│           └── captive-portal  # Service registration (empty marker)
└── src/
    └── captive_portal/   # Python package (all application source)
        ├── __init__.py
        ├── app.py
        ├── middleware.py
        ├── api/
        │   ├── __init__.py
        │   └── routes/   # FastAPI route modules
        ├── config/       # Settings and configuration loading
        ├── controllers/  # External controller adapters (TP-Omada)
        ├── integrations/ # HA client and polling
        ├── models/       # Pydantic/SQLModel data models
        ├── persistence/  # Database engine and repositories
        ├── security/     # Auth, CSRF, RBAC, rate limiting
        ├── services/     # Business logic services
        ├── utils/        # Shared utilities
        └── web/
            ├── middleware/    # HTTP middleware
            ├── templates/    # Jinja2 HTML templates
            │   ├── admin/
            │   ├── guest/
            │   └── portal/
            └── themes/       # CSS theme assets
                └── default/
```

### 1.2 Repository Root (Development Context)

The root is used for development only (tests, linting, type-checking).
It is NOT part of the Docker build context.

```text
/ (repo root)
├── pyproject.toml        # uv workspace config + dev dependencies
├── uv.lock               # Root lock file (dev + workspace)
├── .mypy.ini             # mypy config (mypy_path = addon/src)
├── tests/                # Full test suite
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── performance/
│   └── utils/
├── addon/                # ← Build context (see §1.1)
├── docs/
├── specs/
└── repository.yaml       # HA repository metadata
```

**Note**: The stale `src/` directory at root (containing only empty directories
and `__pycache__`) is removed as part of this refactor.

## 2. Configuration File Models

### 2.1 `addon/config.yaml` (new, replaces config.json)

| Field | Type | Value | Notes |
|---|---|---|---|
| `name` | string | `"Captive Portal Guest Access"` | Display name in HA |
| `version` | string | `"0.0.0-dev"` | Addon version |
| `slug` | string | `"captive_portal_guest_access"` | Unique identifier |
| `description` | string | *(see spec)* | Short description |
| `url` | string | `"https://example.com/placeholder"` | Project URL |
| `arch` | list[string] | `[amd64, aarch64]` | Supported architectures |
| `startup` | string | `"services"` | Startup phase |
| `init` | bool | `false` | No custom init (s6 from base) |
| `panel_admin` | bool | `true` | Show in admin panel |
| `homeassistant_api` | bool | `true` | Needs HA API access |
| `ingress` | bool | `false` | No ingress support |
| `webui` | string | `"http://[HOST]:[PORT:8080]"` | Web UI URL template |
| `ports` | map | `{"8080/tcp": 8080}` | Port mapping |
| `ports_description` | map | `{"8080/tcp": "Web admin & portal"}` | Port labels |
| `schema.log_level` | string | `"list(trace\|debug\|...)\|fatal)?"` | Optional log level |
| `schema.session_idle_timeout` | string | `"int(1,)?"` | Optional idle timeout |
| `schema.session_max_duration` | string | `"int(1,)?"` | Optional max duration |

### 2.2 `addon/build.yaml` (modified)

| Field | Type | Current Value | New Value |
|---|---|---|---|
| `build_from.amd64` | string | `ghcr.io/home-assistant/amd64-base:3.21` | `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21` |
| `build_from.aarch64` | string | `ghcr.io/home-assistant/aarch64-base:3.21` | `ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21` |

### 2.3 `addon/pyproject.toml` (modified)

| Section | Current | New |
|---|---|---|
| `[build-system].requires` | `["setuptools", "wheel"]` | `["hatchling"]` |
| `[build-system].build-backend` | `"setuptools.build_meta"` | `"hatchling.build"` |
| `[tool.setuptools.*]` | Present | Removed entirely |
| `[tool.hatch.build.targets.wheel]` | Absent | `packages = ["src/captive_portal"]` |

### 2.4 `addon/Dockerfile` (modified)

| Aspect | Current | New |
|---|---|---|
| Default `BUILD_FROM` | `ghcr.io/home-assistant/amd64-base:latest` | `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21` |
| Python install | `apk add --no-cache python3` | Removed (base image provides it) |
| Venv strategy | Explicit `uv venv /opt/venv` | uv-managed `.venv` in `/app` |
| Dependency install | `uv pip install --no-cache /app` | Two-phase: `uv sync --frozen --no-dev --no-install-project` then `uv sync --frozen --no-dev` |
| Lock file | Not copied | `COPY uv.lock ./` |
| PATH | `/opt/venv/bin:$PATH` | `/app/.venv/bin:$PATH` |

## 3. File Lifecycle (Create / Modify / Delete)

| Action | File | Reason |
|---|---|---|
| **CREATE** | `addon/config.yaml` | FR-008: YAML format addon metadata |
| **CREATE** | `addon/uv.lock` | FR-020: Frozen dependency lock file |
| **MODIFY** | `addon/Dockerfile` | FR-006, FR-007: Reproducible uv sync pattern |
| **MODIFY** | `addon/build.yaml` | Python-specific base images |
| **MODIFY** | `addon/pyproject.toml` | FR-015: Hatchling build backend |
| **MODIFY** | `addon/rootfs/.../captive-portal/run` | Updated venv path |
| **DELETE** | `addon/config.json` | Replaced by config.yaml |
| **DELETE** | `src/` (root) | Stale empty dirs + __pycache__ only |

## 4. Validation Rules

- `addon/config.yaml` MUST parse as valid YAML and be accepted by HA Supervisor.
- `addon/uv.lock` MUST be generated by `uv lock` and MUST satisfy all
  dependencies in `addon/pyproject.toml`.
- `addon/Dockerfile` with `uv sync --frozen` MUST fail if `uv.lock` is stale
  (this is the `--frozen` guarantee).
- All 441+ existing tests MUST pass from repo root after modifications.
- `ruff`, `mypy`, and `interrogate` MUST pass from repo root.
