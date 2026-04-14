# Quickstart: Migrate Addon Configuration from YAML to Web UI

**Feature**: 012-yaml-to-webui-config
**Date**: 2025-07-18

## Prerequisites

- Python 3.12+
- `uv` package manager
- Git with DCO sign-off configured (`git commit -s`)

## Setup

```bash
# Clone and checkout feature branch
git checkout 012-yaml-to-webui-config

# Install dependencies (adds `cryptography` for Fernet encryption)
uv sync

# Verify existing tests pass before making changes
uv run pytest tests/ -x -q
```

## Key Files to Understand

| File | Purpose |
|------|---------|
| `addon/src/captive_portal/config/settings.py` | AppSettings — currently resolves ALL settings from YAML/env/defaults. Will be simplified. |
| `addon/src/captive_portal/models/portal_config.py` | PortalConfig model — singleton DB record. Will be extended with session/guest fields. |
| `addon/src/captive_portal/config/omada_config.py` | Builds Omada config dict from AppSettings. Will change to read from OmadaConfig DB model. |
| `addon/src/captive_portal/api/routes/portal_settings_ui.py` | Existing settings page — GET/POST with PRG pattern. Will add new form fields. |
| `addon/src/captive_portal/app.py` | App factory with lifespan startup. Will add migration call and Omada reconnection. |
| `addon/src/captive_portal/persistence/database.py` | DB init + lightweight migrations. Will register OmadaConfig and add column migrations. |
| `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run` | Admin service startup script. Will remove Omada env var exports. |
| `addon/config.yaml` | HA addon config schema. Will reduce from 13 to 4 settings. |

## Architecture Patterns

### Follow These Patterns

1. **Singleton DB model**: Use `id=1` primary key pattern (see `PortalConfig`)
2. **PRG form submission**: POST → validate → save → redirect with `?success=` or `?error=`
3. **CSRF double-submit**: Hidden form field + cookie validation
4. **Audit logging**: `AuditService.log_admin_action()` after every config change
5. **Lightweight migration**: `ALTER TABLE ADD COLUMN` in `database.py` init functions
6. **Client-side validation**: Optional JS in `admin-*.js` files; forms must work without JS

### Avoid These Anti-Patterns

1. ❌ Don't store plaintext passwords in the database
2. ❌ Don't send the real password to the browser (use placeholder + `password_changed` flag)
3. ❌ Don't import admin routes in the guest app
4. ❌ Don't block the event loop — use `async` for Omada discovery
5. ❌ Don't overwrite DB values during migration if they already exist

## TDD Workflow

```bash
# 1. Write failing test
uv run pytest tests/unit/models/test_omada_config_model.py -x -v

# 2. Implement minimum code to pass
# ... edit model file ...

# 3. Verify test passes
uv run pytest tests/unit/models/test_omada_config_model.py -x -v

# 4. Run full suite to check for regressions
uv run pytest tests/ -x -q

# 5. Run linting and type checks
uv run ruff check addon/src/ tests/
uv run mypy addon/src/

# 6. Commit with sign-off
git add -A
git commit -s -m "Feat: add OmadaConfig SQLModel for database-backed Omada settings"
```

## Implementation Order

### Phase 1: Omada Settings (User Story 1)
1. `credential_encryption.py` + tests
2. `OmadaConfig` model + tests
3. `omada_settings_ui.py` routes + template + tests
4. Wire into `app.py` lifespan (replace AppSettings-based Omada config)

### Phase 2: Migration (User Story 2)
1. `config_migration.py` service + tests
2. Wire migration into `app.py` lifespan startup
3. Integration tests for migration flow

### Phase 3: Session/Guest Settings (User Story 3)
1. Extend `PortalConfig` model + migration + tests
2. Extend portal settings template and route + tests
3. Wire session config reload on settings save

### Phase 4: YAML Cleanup (User Story 4)
1. Update `addon/config.yaml` schema
2. Simplify s6 run scripts
3. Simplify `AppSettings` (remove migrated fields from resolution)
4. Update all affected tests

## Running Tests

```bash
# Full test suite
uv run pytest tests/ -x -q

# Specific test files
uv run pytest tests/unit/models/test_omada_config_model.py -v
uv run pytest tests/unit/security/test_credential_encryption.py -v
uv run pytest tests/unit/services/test_config_migration.py -v
uv run pytest tests/integration/test_omada_settings_ui.py -v

# With coverage
uv run pytest tests/ --cov=captive_portal --cov-report=term-missing
```

## Useful Commands

```bash
# Check what settings are currently in config.yaml
cat addon/config.yaml | grep -A 20 "^schema:"

# Check s6 run scripts for env var exports
grep "export CP_" addon/rootfs/etc/s6-overlay/s6-rc.d/*/run

# Find all templates with navigation (need updating for "Omada" link)
grep -l "nav-link" addon/src/captive_portal/web/templates/admin/*.html

# Find all files importing AppSettings (may need updating)
grep -rl "from captive_portal.config.settings import" addon/src/

# Count current tests
find tests/ -name "*.py" -exec grep -l "def test_" {} \; | wc -l
```
