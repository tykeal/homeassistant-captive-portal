SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Integrations Auto-Detection

**Feature**: 006-integrations-auto-detect | **Date**: 2025-07-14

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on `006-integrations-auto-detect` branch

## Setup

```bash
# Clone and switch to feature branch
cd <your-clone>
git checkout 006-integrations-auto-detect

# Install dependencies (dev group includes test tools)
uv sync --group dev
```

## Run Tests

```bash
# Run all tests
uv run pytest tests/ -x -q

# Run only unit tests
uv run pytest tests/unit/ -x -q

# Run only integration tests
uv run pytest tests/integration/ -x -q

# Run contract tests (HA API contracts)
uv run pytest tests/contract/ -x -q -m contract

# Run with coverage
uv run pytest tests/ --cov=captive_portal --cov-report=term-missing

# Run specific test files for this feature (once implementation is complete)
# uv run pytest tests/unit/integrations/test_ha_discovery_service.py -x -v
# uv run pytest tests/integration/test_integrations_auto_detect.py -x -v
# uv run pytest tests/contract/ha/test_entity_discovery.py -x -v
```

## Lint & Type Check

```bash
# Lint
uv run ruff check addon/src/ tests/

# Format check
uv run ruff format --check addon/src/ tests/

# Type check
uv run mypy addon/src/

# Docstring coverage (100% required, runs via pre-commit)
uv tool run interrogate addon/src/ -v
```

## Run Locally (for manual testing)

```bash
# Start the admin app on port 8080
# Note: Without a real HA Supervisor, the discovery will fall back to manual entry
uv run uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Admin UI pages:
#   Login:        http://localhost:8080/admin/login
#   Dashboard:    http://localhost:8080/admin/dashboard
#   Integrations: http://localhost:8080/admin/integrations  ← this feature
#   Grants:       http://localhost:8080/admin/grants
#   Vouchers:     http://localhost:8080/admin/vouchers
#   Settings:     http://localhost:8080/admin/portal-settings

# To simulate HA API for local testing, set environment variables:
# export SUPERVISOR_TOKEN="test-token"
# export CP_HA_BASE_URL="http://localhost:8123/api"
# Then have a local HA instance running with Rental Control integrations
```

## Key Files for This Feature

### New Files to Create
| File | Purpose |
|------|---------|
| `addon/src/captive_portal/integrations/ha_discovery_service.py` | Discovery service: query HA, filter entities, build view models |
| `addon/src/captive_portal/web/themes/default/admin-integrations.js` | Progressive enhancement: refresh button fetch + dropdown update |
| `tests/unit/integrations/test_ha_discovery_service.py` | Unit tests for discovery service (mocked HA API) |
| `tests/integration/test_integrations_auto_detect.py` | Integration tests for page + discovery flow |

### Existing Files to Modify
| File | Change |
|------|--------|
| `addon/src/captive_portal/integrations/ha_client.py` | Add `get_all_states()` method |
| `addon/src/captive_portal/api/routes/integrations.py` | Add `GET /api/integrations/discover` endpoint |
| `addon/src/captive_portal/api/routes/integrations_ui.py` | Call discovery service, pass results to template |
| `addon/src/captive_portal/web/templates/admin/integrations.html` | Replace free-text input with pick-list + manual fallback |
| `addon/src/captive_portal/web/themes/default/admin.css` | Add styles: loading indicator, status badges, empty state |
| `tests/contract/ha/test_entity_discovery.py` | Implement existing skipped contract tests |
| `tests/conftest.py` | Add HA API mock fixtures |

## Development Workflow

Follow constitution-mandated TDD:

1. **Red**: Write a failing test for the next behavior
2. **Green**: Write minimum code to make the test pass
3. **Refactor**: Clean up while keeping tests green
4. **Lint**: `uv run ruff check` + `uv run mypy`
5. **Commit**: `git commit -s -m "Type(scope): Description"`

## Suggested Implementation Order

> **Note**: `specs/006-integrations-auto-detect/tasks.md` is the authoritative execution
> order. The summary below is a simplified overview.

1. **Phase 1 — HAClient Extension**: Add `get_all_states()` to `HAClient` + unit tests
2. **Phase 2 — Discovery Service**: Create `HADiscoveryService` + view models + unit tests
3. **Phase 3 — Discovery API Endpoint**: Add `GET /api/integrations/discover` + tests
4. **Phase 4 — UI Route Modification**: Update `integrations_ui.py` to call discovery + tests
5. **Phase 5 — Template Update**: Replace free-text with pick-list + manual fallback + styles
6. **Phase 6 — Progressive Enhancement**: Add `admin-integrations.js` for refresh button
7. **Phase 7 — Contract Tests**: Implement existing skipped HA contract tests
8. **Phase 8 — Polish**: Integration tests, edge cases, accessibility, full test sweep
