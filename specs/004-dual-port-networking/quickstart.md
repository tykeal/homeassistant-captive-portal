SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Dual-Port Networking

**Feature**: 004-dual-port-networking
**Date**: 2025-07-15

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Repository cloned and on the `004-dual-port-networking` branch

## Setup

```bash
# Clone and checkout
git clone <repo-url>
cd <repo-directory>
git checkout 004-dual-port-networking

# Install dependencies (including dev tools)
uv sync
```

## Running Tests

```bash
# All tests (existing + new dual-port tests)
uv run pytest

# Only unit tests
uv run pytest tests/unit/

# Only integration tests
uv run pytest -m integration

# Only dual-port-specific tests (after implementation)
uv run pytest tests/unit/test_guest_app_factory.py tests/unit/test_guest_app_routes.py
uv run pytest tests/integration/test_dual_port_isolation.py
```

## Linting & Type Checks

```bash
# Ruff linting
uv run ruff check .

# Mypy type checking
uv run mypy addon/src/captive_portal/

# All pre-commit hooks
uv run pre-commit run --all-files
```

## Architecture Overview

### Two Listeners, Two Apps, One Database

```
┌──────────────────┐    ┌────────────────────┐
│ Ingress Listener │    │  Guest Listener    │
│ Port 8080        │    │  Port 8099         │
│                  │    │                    │
│ create_app()     │    │ create_guest_app() │
│ All routes       │    │ Guest routes only  │
│ HA auth proxy    │    │ No auth required   │
└────────┬─────────┘    └──────────┬─────────┘
         │                         │
         └──────────┬──────────────┘
                    │
            ┌───────▼───────┐
            │  SQLite DB    │
            └───────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `addon/src/captive_portal/app.py` | Ingress app factory (existing, unchanged) |
| `addon/src/captive_portal/guest_app.py` | Guest app factory (new) |
| `addon/src/captive_portal/config/settings.py` | Settings with `guest_external_url` field |
| `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run` | Ingress service script (unchanged) |
| `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/run` | Guest service script (new) |
| `addon/config.yaml` | Addon config with 8099/tcp port + schema |

### Route Policy

- **Ingress app** (`create_app`): All routers — admin, guest, detection, health, docs
- **Guest app** (`create_guest_app`): Only `guest_portal`, `captive_detect`, `booking_authorize`, `health` routers
- Admin routes return **404 Not Found** on guest port (not 401/403)

## Testing the Guest App Locally

```python
# In a test or REPL
from captive_portal.guest_app import create_guest_app
from captive_portal.config.settings import AppSettings
from fastapi.testclient import TestClient

settings = AppSettings(db_path=":memory:")
app = create_guest_app(settings=settings)
client = TestClient(app)

# Guest route works
response = client.get("/guest/authorize")
assert response.status_code == 200

# Admin route returns 404 (not 401)
response = client.get("/admin/portal-settings/")
assert response.status_code == 404

# Captive detection redirects
response = client.get("/generate_204", follow_redirects=False)
assert response.status_code == 302
assert "/guest/authorize" in response.headers["location"]

# Health endpoint works
response = client.get("/api/health")
assert response.status_code == 200
```

## Addon Configuration

After implementation, the addon `config.yaml` will expose:

```yaml
ports:
  "8080/tcp": null   # Ingress (HA-managed)
  "8099/tcp": 8099   # Guest portal (configurable via HA UI)

schema:
  guest_external_url: "url?"   # e.g., http://192.168.1.100:8099
```

Administrators configure `guest_external_url` in the addon settings to match
the address their WiFi controller uses for captive portal redirection.

## Development Workflow

1. **Write a failing test** for the guest app behavior
2. **Implement** `create_guest_app()` to make it pass
3. **Refactor** while keeping all tests green
4. **Run linting/type checks** (`ruff check .`, `mypy`)
5. **Commit** with SPDX headers, DCO sign-off, Conventional Commits
