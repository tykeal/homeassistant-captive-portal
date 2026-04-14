# Implementation Plan: Migrate Addon Configuration from YAML to Web UI

**Branch**: `012-yaml-to-webui-config` | **Date**: 2025-07-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-yaml-to-webui-config/spec.md`

## Summary

Migrate nine addon settings currently configured via YAML (`/data/options.json`) to database-backed web UI management. This creates a new `OmadaConfig` model for Omada controller settings (with Fernet-encrypted password storage), extends the existing `PortalConfig` model with session timeout and guest URL fields, adds a one-time startup migration service, builds two new admin UI pages (Omada Settings + extended Portal Settings), updates s6 run scripts to stop exporting migrated env vars, and simplifies the YAML schema to four startup-only settings.

## Technical Context

**Language/Version**: Python 3.12+ with full type annotation coverage (mypy strict)
**Primary Dependencies**: FastAPI 0.115+, SQLModel, Jinja2, Pydantic v2, cryptography (Fernet), httpx
**Storage**: SQLite via SQLModel/SQLAlchemy (file: `/data/captive_portal.db`)
**Testing**: pytest with pytest-asyncio; ~1390 existing tests (174 test files)
**Target Platform**: Home Assistant addon (Linux amd64/aarch64, s6-overlay)
**Project Type**: Web service (FastAPI admin + guest portals)
**Performance Goals**: Settings save <200ms; migration completes in <1s on startup
**Constraints**: All 1390+ tests must pass; EVERY migrated setting must have working UI
**Scale/Scope**: Single-instance addon; singleton config records; 6 Omada fields + 3 session/guest fields to migrate

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality (NON-NEGOTIABLE) | ✅ PASS | All new code will include docstrings, type annotations, pass ruff/mypy. Complexity <10. SPDX headers on all files. |
| II. Test-Driven Development (NON-NEGOTIABLE) | ✅ PASS | TDD red-green-refactor for all new models, services, routes. Existing 1390+ tests must remain green. |
| III. User Experience Consistency | ✅ PASS | New forms follow existing PRG pattern, flash messages, nav structure, CSRF. Consistent naming/layout. |
| IV. Performance Requirements | ✅ PASS | Settings CRUD is lightweight; no impact on voucher/grant performance paths. |
| V. Atomic Commits & Compliance (NON-NEGOTIABLE) | ✅ PASS | Each commit = one logical change, DCO sign-off, SPDX headers, pre-commit hooks. |
| VI. Phased Development | ✅ PASS | Four phases aligned with user stories (P1–P4), each independently testable. |
| Security: Passwords | ⚠️ DEVIATION | Constitution says "Argon2 hashing" but spec requires **reversible encryption** for Omada password (used as credential). Fernet symmetric encryption used instead. See Complexity Tracking. |

## Project Structure

### Documentation (this feature)

```text
specs/012-yaml-to-webui-config/
├── plan.md              # This file
├── research.md          # Phase 0 output — encryption, migration, UI decisions
├── data-model.md        # Phase 1 output — OmadaConfig model, PortalConfig extensions
├── quickstart.md        # Phase 1 output — developer onboarding
├── contracts/           # Phase 1 output — API endpoint contracts
│   ├── omada-settings-ui.md
│   └── portal-settings-extensions.md
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── config/
│   ├── settings.py              # MODIFY — remove migrated fields from resolution, add DB read
│   └── omada_config.py          # MODIFY — accept OmadaConfig model instead of AppSettings
├── models/
│   ├── portal_config.py         # MODIFY — add session_idle_minutes, session_max_hours, guest_external_url
│   └── omada_config.py          # NEW — OmadaConfig SQLModel with encrypted password
├── persistence/
│   └── database.py              # MODIFY — register OmadaConfig, add migration function
├── security/
│   └── credential_encryption.py # NEW — Fernet encrypt/decrypt for Omada password
├── services/
│   └── config_migration.py      # NEW — one-time YAML→DB migration service
├── api/routes/
│   ├── portal_settings_ui.py    # MODIFY — add session/guest URL fields to form
│   ├── omada_settings_ui.py     # NEW — Omada settings page (GET/POST)
│   └── portal_config.py         # MODIFY — extend API response/update models
├── web/
│   ├── templates/admin/
│   │   ├── portal_settings.html # MODIFY — add session timeout + guest URL sections
│   │   └── omada_settings.html  # NEW — Omada controller configuration form
│   └── themes/default/
│       ├── admin-portal-settings.js  # MODIFY — add validation for new fields
│       └── admin-omada-settings.js   # NEW — Omada form client-side validation
├── app.py                       # MODIFY — run migration in lifespan, reload Omada on save
└── guest_app.py                 # MODIFY — read Omada/session config from DB

addon/rootfs/etc/s6-overlay/s6-rc.d/
├── captive-portal/run           # MODIFY — remove Omada env var exports
└── captive-portal-guest/run     # MODIFY — remove Omada + guest URL env var exports

addon/config.yaml                # MODIFY — reduce schema to 4 startup-only settings

tests/
├── unit/
│   ├── models/
│   │   └── test_omada_config_model.py   # NEW
│   ├── security/
│   │   └── test_credential_encryption.py # NEW
│   ├── services/
│   │   └── test_config_migration.py      # NEW
│   └── config/
│       └── test_settings.py              # MODIFY — update for reduced field set
└── integration/
    ├── test_omada_settings_ui.py         # NEW
    ├── test_portal_settings_extended.py  # NEW
    └── test_config_migration_e2e.py      # NEW
```

**Structure Decision**: Follows existing project layout. New files placed in established directories (`models/`, `security/`, `services/`, `api/routes/`). No new top-level packages introduced.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Fernet encryption instead of Argon2 hashing for Omada password | The Omada password is a credential sent to the controller API — the system must decrypt it to use it. One-way hashing would make the password unrecoverable. | Argon2 is appropriate for admin login passwords (verification only). Omada password requires reversible encryption (Fernet with machine-local key). |
