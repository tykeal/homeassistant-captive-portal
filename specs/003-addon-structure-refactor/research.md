SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Addon Structure Refactor (003)

**Feature Branch**: `003-addon-structure-refactor`
**Date**: 2025-07-15

## 1. Build Backend: Hatchling vs Setuptools

**Decision**: Switch from `setuptools` to `hatchling` as the PEP 517 build backend.

**Rationale**: The reference HA addon (rentalsync-bridge) uses hatchling. Hatchling
provides a modern, standards-compliant build backend that works seamlessly with
`uv sync --frozen`. Setuptools requires the legacy `wheel` co-dependency and uses
the non-standard `tool.setuptools` configuration namespace. Hatchling is
purpose-built for modern Python packaging and has first-class support in uv.

**Alternatives considered**:
- **Setuptools** (current): Works but requires `wheel` as co-build-dependency,
  uses non-standard configuration keys (`tool.setuptools.packages.find`), and
  does not integrate as cleanly with `uv sync --frozen` for lock-file-based
  installs.
- **Flit**: Simpler than hatchling but lacks the `tool.hatch.build.targets.wheel`
  configuration needed for non-standard source layouts (`src/` subdirectory).
- **PDM**: Heavier than needed; introduces its own lock format.

**Key configuration change**: The `[tool.setuptools.packages.find]` and
`[tool.setuptools.package-data]` sections must be replaced with
`[tool.hatch.build.targets.wheel]` to configure the `src/` package layout and
include static assets (HTML templates, CSS themes).

---

## 2. Base Container Image: Python-Specific vs Generic

**Decision**: Switch from generic HA base images (`*-base:3.21`) to
Python-specific HA base images (`*-base-python:3.13-alpine3.21`).

**Rationale**: The reference addon uses Python-specific base images, which
pre-install Python 3.x and the standard library. This eliminates the
`apk add --no-cache python3` step in the Dockerfile, reduces build time, and
ensures a consistent Python version across architectures. The captive-portal
requires Python ≥ 3.12; the HA Python base images currently ship Python 3.13
on Alpine 3.21, which satisfies that constraint.

**Alternatives considered**:
- **Generic base + apk install** (current): Adds build time and couples the
  Python version to whatever Alpine's repos provide, which may drift between
  base image releases.
- **Multi-stage build with official Python image**: Overly complex for an HA
  addon; the HA base images already include s6-overlay and bashio.

**Architecture mapping**:
| Architecture | Base image |
|---|---|
| amd64 | `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21` |
| aarch64 | `ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21` |

---

## 3. Dockerfile Pattern: `uv sync --frozen` vs `uv pip install`

**Decision**: Adopt the two-phase `uv sync --frozen` pattern from the reference.

**Rationale**: The reference Dockerfile separates dependency installation from
project installation:
1. Copy `pyproject.toml` + `uv.lock` → `uv sync --frozen --no-dev --no-install-project`
2. Copy source code → `uv sync --frozen --no-dev`

This pattern enables Docker layer caching: when only source code changes, step 1
is cached and only step 2 re-runs. The `--frozen` flag ensures the lock file is
respected exactly, fulfilling FR-006 (reproducible, lock-file-based builds).
The current `uv pip install --no-cache /app` pattern does not use the lock file
and resolves dependencies at build time, making builds non-deterministic.

**Alternatives considered**:
- **`uv pip install` with constraints file**: Possible but non-standard; the
  lock file approach is the idiomatic uv workflow.
- **`uv pip install --frozen`**: Does not exist; `--frozen` is a `uv sync` flag.

**Key Dockerfile changes**:
- Remove `apk add --no-cache python3` (Python base image provides it)
- Remove explicit `uv venv` + `VIRTUAL_ENV` management (uv sync creates `.venv`
  automatically in the project directory)
- Use `uv sync --frozen --no-dev --no-install-project` for deps, then
  `uv sync --frozen --no-dev` for the full project
- Set `PATH="/app/.venv/bin:$PATH"` after install
- Copy `uv.lock` alongside `pyproject.toml`

---

## 4. Addon Config Format: JSON → YAML

**Decision**: Convert `addon/config.json` to `addon/config.yaml`, preserving
all semantic content exactly.

**Rationale**: FR-008 requires YAML format to follow HA addon conventions. The
HA documentation and most community addons use `config.yaml`. The reference
addon uses `config.yaml`. The conversion is a format change only with no
semantic modifications per the spec's assumption.

**Alternatives considered**:
- **Keep JSON**: Technically supported by HA Supervisor but non-conventional.
  The spec explicitly requires YAML (FR-008).
- **Hybrid (both files)**: Unnecessary; HA Supervisor reads one or the other.

**Conversion notes**:
- `init: false` in JSON maps to `init: false` in YAML (boolean).
- `panel_admin: true` maps to `panel_admin: true`.
- Port mapping `"8080/tcp": 8080` maps to `"8080/tcp": 8080` (quoted key).
- Schema section maps directly to YAML.
- The `startup: services` value is preserved.
- The old `config.json` must be removed after `config.yaml` is created.

---

## 5. Addon Lock File Strategy

**Decision**: Generate `addon/uv.lock` as a regular file managed by
`uv lock` inside the addon workspace member, and maintain it as part of
the development workflow.

**Rationale**: FR-020 requires a lock file in `addon/` for reproducible
container builds. The spec's assumption explicitly states it MUST be a regular
file (not a symlink). The reference addon has `uv.lock` inside its addon
directory. Since the root `pyproject.toml` already declares `addon` as a
workspace member, running `uv lock` from root will generate/update both the
root `uv.lock` (for dev) and ensure the addon's dependencies are resolved.
However, the addon also needs its own `uv.lock` for the Dockerfile's
`uv sync --frozen` to work within the `addon/` build context.

**Generation approach**: Run `cd addon && uv lock` to generate `addon/uv.lock`
from the addon's `pyproject.toml`. This lock file pins all runtime dependencies
and is copied into the Docker build context.

**Alternatives considered**:
- **Symlink to root uv.lock**: Explicitly prohibited by spec assumptions;
  symlinks don't resolve inside the Docker build context.
- **Copy root uv.lock at build time**: Fragile and requires a build script;
  the lock formats may diverge since root has dev dependencies.

---

## 6. Stale Root `src/` Directory Cleanup

**Decision**: Remove the stale `src/captive_portal/` directory tree at the
repository root, which contains only empty directories and `__pycache__` bytecode.

**Rationale**: The source code has already been relocated to `addon/src/captive_portal/`.
The root `src/` directory now contains only empty subdirectories and compiled
`__pycache__` artifacts that are stale and confusing. The root `pyproject.toml`
uses a workspace configuration that references `addon` as a member, so the root
`src/` serves no purpose. Removing it eliminates confusion about where the
canonical source lives.

**Alternatives considered**:
- **Keep as-is**: Confusing for developers; `src/` at root suggests that's where
  code lives.
- **Make it a proper symlink**: Fragile and unnecessary given the workspace config.

---

## 7. Package Data Inclusion with Hatchling

**Decision**: Use `[tool.hatch.build.targets.wheel]` with `packages = ["src/captive_portal"]`
and ensure non-Python files (HTML templates, CSS themes) are included via hatch's
default inclusion behavior.

**Rationale**: Hatchling includes all files in the package directory by default
(unlike setuptools which requires explicit `package-data` configuration). The
reference addon uses `packages = ["src"]` because its source code lives directly
under `src/`. For captive-portal, the source is at `src/captive_portal/`, so the
hatch wheel target should point there. HTML templates at
`src/captive_portal/web/templates/` and CSS themes at
`src/captive_portal/web/themes/` will be included automatically.

**Alternatives considered**:
- **Explicit `include` patterns**: Unnecessary since hatch includes all files in
  the declared package directories by default.
- **Separate `MANIFEST.in`**: Setuptools artifact; not used by hatchling.

---

## 8. s6-overlay Service Configuration Assessment

**Decision**: Keep the existing s6-overlay service definitions largely as-is.
The current `captive-portal` service under `rootfs/etc/s6-overlay/s6-rc.d/`
already follows the correct pattern with `run`, `finish`, and `type` files.

**Rationale**: The existing configuration already satisfies FR-011 (s6-overlay),
FR-012 (long-running with auto-restart via `type` = `longrun`), and FR-013
(port 8080 binding). The `finish` script logs unexpected exit codes, which the
reference addon lacks — this is an enhancement worth keeping. The only change
needed is updating the `run` script to use the new venv path (`/app/.venv/bin/python`
instead of `${VIRTUAL_ENV}/bin/python`) once the Dockerfile switches from
explicit venv management to uv-managed `.venv`.

**Alternatives considered**:
- **Strip to minimal (reference pattern)**: Would lose the `finish` script's
  error logging, which is a useful feature for debugging.
- **Add `dependencies.d/`**: The reference has an empty `dependencies.d/`
  directory. Not strictly needed unless there are inter-service dependencies.

---

## 9. Development Workflow Impact Assessment

**Decision**: The root-level `pyproject.toml` workspace configuration and
`.mypy.ini` already correctly reference `addon/src` as the source path. No
changes needed to the development workflow beyond ensuring `addon/uv.lock`
stays in sync when dependencies change.

**Rationale**: The root `pyproject.toml` declares `[tool.uv.workspace] members = ["addon"]`
and `[tool.uv.sources] captive-portal = { workspace = true }`. The `.mypy.ini`
has `mypy_path = addon/src`. Tests import `captive_portal` which resolves through
the workspace. This setup is already working. The build backend change in
`addon/pyproject.toml` (setuptools → hatchling) may require a `uv sync` to
update the editable install, but no test modifications are needed.

**Risk**: Switching from setuptools to hatchling changes how the package is
discovered. Need to verify all 441+ tests still pass after the switch.
