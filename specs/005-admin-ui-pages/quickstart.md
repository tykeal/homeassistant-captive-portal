SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Admin UI Pages

**Feature**: 005-admin-ui-pages | **Date**: 2025-07-16

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on `005-admin-ui-pages` branch

## Setup

```bash
# Clone and switch to feature branch
cd <your-clone>
git checkout 005-admin-ui-pages

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

# Run with coverage
uv run pytest tests/ --cov=captive_portal --cov-report=term-missing

# Run specific test files for this feature (once implementation is complete)
# uv run pytest tests/unit/routes/test_dashboard_ui.py -x -v
# uv run pytest tests/unit/routes/test_grants_ui.py -x -v
# uv run pytest tests/unit/routes/test_vouchers_ui.py -x -v
# uv run pytest tests/unit/routes/test_admin_logout_ui.py -x -v
# uv run pytest tests/integration/test_admin_dashboard_page.py -x -v
# uv run pytest tests/integration/test_admin_grants_page.py -x -v
# uv run pytest tests/integration/test_admin_vouchers_page.py -x -v
# uv run pytest tests/integration/test_admin_logout_flow.py -x -v
# uv run pytest tests/integration/test_admin_cache_headers.py -x -v
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
# interrogate is not in dev deps; use pre-commit or uv tool:
uv tool run interrogate addon/src/ -v
```

## Run Locally (for manual testing)

```bash
# Start the admin app on port 8080
uv run uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Admin UI pages:
#   Login:      http://localhost:8080/admin/login
#   Dashboard:  http://localhost:8080/admin/dashboard
#   Grants:     http://localhost:8080/admin/grants
#   Vouchers:   http://localhost:8080/admin/vouchers
#   Settings:   http://localhost:8080/admin/portal-settings
#   Integrations: http://localhost:8080/admin/integrations
```

## Key Files for This Feature

### New Files to Create
| File | Purpose |
|------|---------|
| `addon/src/captive_portal/api/routes/dashboard_ui.py` | Dashboard page route handler |
| `addon/src/captive_portal/api/routes/grants_ui.py` | Grants page + extend/revoke handlers |
| `addon/src/captive_portal/api/routes/vouchers_ui.py` | Vouchers page + create handler |
| `addon/src/captive_portal/api/routes/admin_logout_ui.py` | Logout HTML handler |
| `addon/src/captive_portal/services/dashboard_service.py` | Dashboard statistics aggregation |
| `addon/src/captive_portal/web/templates/admin/vouchers.html` | Vouchers page template |

### Existing Files to Modify
| File | Change |
|------|--------|
| `addon/src/captive_portal/app.py` | Register 4 new route modules |
| `addon/src/captive_portal/web/middleware/security_headers.py` | Add cache-control for `/admin/*` |
| `addon/src/captive_portal/web/templates/admin/dashboard.html` | Empty states, timestamp field fix |
| `addon/src/captive_portal/web/templates/admin/grants_enhanced.html` | Feedback messages, empty states, disable expired grant extend |
| `addon/src/captive_portal/web/templates/admin/portal_settings.html` | Logout form action update |
| `addon/src/captive_portal/web/templates/admin/integrations.html` | Logout form action update |
| `addon/src/captive_portal/web/themes/default/admin.css` | Alert, empty-state, voucher-code styles |

## Development Workflow

Follow constitution-mandated TDD:

1. **Red**: Write a failing test for the next behavior
2. **Green**: Write minimum code to make the test pass
3. **Refactor**: Clean up while keeping tests green
4. **Lint**: `uv run ruff check` + `uv run mypy`
5. **Commit**: `git commit -s -m "Type(scope): Description"`

## Suggested Implementation Order

1. `dashboard_service.py` + tests (foundation for dashboard)
2. `dashboard_ui.py` + update `dashboard.html` + tests
3. `grants_ui.py` + update `grants_enhanced.html` + tests
4. `vouchers_ui.py` + create `vouchers.html` + tests
5. `admin_logout_ui.py` + update all templates' logout forms + tests
6. Cache-control headers in `security_headers.py` + tests
7. Register all new routes in `app.py`
8. Full integration test sweep
