SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Addon Structure Refactor (003)

**Feature Branch**: `003-addon-structure-refactor`
**Date**: 2025-07-15

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- Git

### Clone and Install

```bash
git clone <repo-url>
cd <repo-dir>
git checkout 003-addon-structure-refactor

# Install all dependencies (workspace resolves addon as editable)
uv sync
```

### Run Tests

```bash
# Full test suite from repo root
uv run pytest

# With coverage
uv run pytest --cov=captive_portal --cov-report=term-missing

# Specific test categories
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest -m "not performance"
```

### Run Linting and Type Checks

```bash
# Ruff linting
uv run ruff check addon/src/ tests/

# Ruff formatting check
uv run ruff format --check addon/src/ tests/

# Mypy type checking (uses .mypy.ini at root)
uv run mypy addon/src/captive_portal/

# Interrogate docstring coverage
uv run interrogate addon/src/captive_portal/
```

## Addon Build (Local Docker)

### Build the Container Image

```bash
# From repo root, targeting addon/ as build context
docker build -t captive-portal:dev addon/

# For a specific architecture (if on amd64, this is the default)
docker build \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21 \
  -t captive-portal:dev addon/
```

### Run the Container Locally

```bash
docker run --rm -p 8080:8080 captive-portal:dev

# Verify it's running
curl http://localhost:8080/api/health
```

### Test on Home Assistant

1. Add the repository URL to HA → Settings → Add-ons → Add-on Store → ⋮ → Repositories
2. Find "Captive Portal Guest Access" in the store
3. Click Install → Start
4. Verify the admin panel link appears and the web interface loads

## Addon Dependency Management

### Update Runtime Dependencies

When changing dependencies in `addon/pyproject.toml`:

```bash
# Regenerate the addon lock file
cd addon
uv lock
cd ..

# Regenerate root lock file (workspace)
uv lock

# Verify tests still pass
uv sync
uv run pytest
```

### Key File Locations

| Purpose | Path |
|---|---|
| Application source code | `addon/src/captive_portal/` |
| Addon Dockerfile | `addon/Dockerfile` |
| Addon config (HA metadata) | `addon/config.yaml` |
| Addon build config | `addon/build.yaml` |
| Addon package definition | `addon/pyproject.toml` |
| Addon dependency lock | `addon/uv.lock` |
| s6 service scripts | `addon/rootfs/etc/s6-overlay/s6-rc.d/` |
| Dev workspace config | `pyproject.toml` (root) |
| Dev dependency lock | `uv.lock` (root) |
| Tests | `tests/` |
| Mypy config | `.mypy.ini` |

## Architecture Notes

- **Workspace model**: The root `pyproject.toml` declares `addon` as a uv
  workspace member. Running `uv sync` from root installs `captive-portal`
  as an editable package, making `import captive_portal` work in tests.
- **Dual lock files**: `uv.lock` (root) covers dev + runtime deps for the
  workspace. `addon/uv.lock` covers only runtime deps for the Docker build.
- **Build context isolation**: The `addon/` directory is self-contained for
  Docker builds. Nothing outside `addon/` is available during `docker build`.
- **s6-overlay**: The HA base images include s6-overlay. The `rootfs/` overlay
  adds the `captive-portal` service definition, which s6 starts automatically.
