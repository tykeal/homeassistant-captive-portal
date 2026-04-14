# Tasks: Migrate Addon Configuration from YAML to Web UI

**Input**: Design documents from `/specs/012-yaml-to-webui-config/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — the spec mandates TDD (Constitution Principle II) and SC-007 requires complete test coverage for all migrated settings.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Tests**: `tests/unit/`, `tests/integration/`
- **Templates**: `addon/src/captive_portal/web/templates/admin/`
- **JS**: `addon/src/captive_portal/web/themes/default/`
- **s6 scripts**: `addon/rootfs/etc/s6-overlay/s6-rc.d/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the `cryptography` dependency and create the credential encryption module that User Stories 1 and 2 both depend on.

- [ ] T001 Add `cryptography` as explicit dependency in `addon/pyproject.toml` under `[project.dependencies]` and run `uv lock` to update `uv.lock`
- [ ] T002 [P] Write unit tests for Fernet credential encryption in `tests/unit/security/test_credential_encryption.py` — cover: key auto-generation, encrypt/decrypt round-trip, empty plaintext rejection, invalid ciphertext error, key file permissions (0o600), key reuse across calls
- [ ] T003 [P] Implement Fernet credential encryption module in `addon/src/captive_portal/security/credential_encryption.py` — functions: `encrypt_credential(plaintext, key_path)` → ciphertext, `decrypt_credential(ciphertext, key_path)` → plaintext, `_load_or_create_key(key_path)` → bytes; key stored at configurable path (default `/data/.omada_key`), auto-generated if missing, chmod 0o600; raise `ValueError` on empty input

**Verification**: Run `uv run pytest tests/unit/security/test_credential_encryption.py -v` — all tests pass. Run `uv run mypy addon/src/captive_portal/security/credential_encryption.py` — no errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Register the new OmadaConfig model in the database module so table creation and migrations are in place before any user story work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Register `OmadaConfig` model import in `addon/src/captive_portal/persistence/database.py` — add import of `OmadaConfig` from `captive_portal.models.omada_config`, add to `__all__` list, so SQLModel metadata creates the `omada_config` table during `init_db()`
- [ ] T005 Add lightweight `ALTER TABLE` migration function `_migrate_portal_config_session_fields(engine)` in `addon/src/captive_portal/persistence/database.py` — add columns `session_idle_minutes INTEGER DEFAULT 30`, `session_max_hours INTEGER DEFAULT 8`, `guest_external_url VARCHAR(2048) DEFAULT ''` to `portal_config` table if they don't exist; call from `init_db()` after `SQLModel.metadata.create_all()`

**Checkpoint**: Foundation ready — `init_db()` now creates `omada_config` table and adds session/guest columns to `portal_config`. User story implementation can now begin.

---

## Phase 3: User Story 1 — Configure Omada Controller via Web UI (Priority: P1) 🎯 MVP

**Goal**: Admin can configure Omada controller settings (URL, username, password, site name, controller ID, SSL verification) through a new web UI page at `/admin/omada-settings/`. Settings are encrypted and persisted to DB. Saving triggers Omada reconnection without addon restart.

**Independent Test**: Navigate to `/admin/omada-settings/`, enter controller details, save, verify flash message confirms save, and confirm `app.state.omada_config` is rebuilt from DB. Password is never visible in page source.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T006 [P] [US1] Write unit tests for OmadaConfig model in `tests/unit/models/test_omada_config_model.py` — cover: default values (id=1, controller_url="", site_name="Default", verify_ssl=True), field max lengths, `omada_configured` computed property (true when url+username+encrypted_password all non-empty, false otherwise), singleton pattern
- [ ] T007 [P] [US1] Write integration tests for Omada settings UI in `tests/integration/test_omada_settings_ui.py` — cover: GET renders form with CSRF token and all fields; GET shows masked password placeholder when password stored; POST saves valid settings and redirects with success message; POST with `password_changed=false` preserves existing encrypted password; POST with invalid URL returns error redirect; POST with empty controller_url+username saves cleared config; POST triggers `app.state.omada_config` rebuild; POST logs audit event `omada_config.update`; navigation bar includes "Omada" link on all admin pages

### Implementation for User Story 1

- [ ] T008 [US1] Create OmadaConfig SQLModel in `addon/src/captive_portal/models/omada_config.py` — fields: `id` (int, PK, default=1), `controller_url` (str, max 2048, default=""), `username` (str, max 255, default=""), `encrypted_password` (str, max 1024, default=""), `site_name` (str, max 255, default="Default"), `controller_id` (str, max 64, default=""), `verify_ssl` (bool, default=True); add `@property omada_configured` returning bool; add `__tablename__ = "omada_config"` and `model_config = {"validate_assignment": True}`
- [ ] T009 [US1] Create the complete Omada settings page — all of the following in one task:
  - **Route**: Create `addon/src/captive_portal/api/routes/omada_settings_ui.py` with `router = APIRouter(prefix="/admin/omada-settings")`:
    - `GET /` — load `OmadaConfig(id=1)` from DB (create default if missing), render template with context: `config`, `csrf_token`, `has_password` (bool from `encrypted_password`), `success_message`, `error_message`
    - `POST /` — validate CSRF; validate `controller_url` (http/https or empty), `username` (required if url set), `controller_id` (hex pattern `^[a-fA-F0-9]{12,64}$` or empty), `site_name` (default "Default"); if `password_changed=="true"` and password non-empty: encrypt via `encrypt_credential()` and store; if `password_changed=="false"`: preserve existing `encrypted_password`; persist to DB; rebuild `app.state.omada_config` via `build_omada_config()`; log audit event `omada_config.update` (redact password); redirect with success/error query param
  - **Template**: Create `addon/src/captive_portal/web/templates/admin/omada_settings.html` — full HTML page matching existing admin style with nav bar (Dashboard, Grants, Vouchers, Integrations, **Omada** [active], Settings, Logout); form with fields: `controller_url` (type=url), `username` (type=text), `password` (type=password, never pre-filled, placeholder "••••••••" if `has_password`), `password_changed` (hidden, default "false"), `site_name` (type=text), `controller_id` (type=text, placeholder "Leave empty for auto-discovery"), `verify_ssl` (checkbox, checked by default); CSRF hidden field; success/error flash messages
  - **JS validation**: Create `addon/src/captive_portal/web/themes/default/admin-omada-settings.js` — validate URL format for `controller_url`, set `password_changed` hidden field to "true" on password input event, validate `controller_id` hex pattern if non-empty
  - **Register route**: Add `omada_settings_ui.router` to the admin app router includes in `addon/src/captive_portal/app.py`
- [ ] T010 [US1] Update `addon/src/captive_portal/config/omada_config.py` to accept `OmadaConfig` model — modify `build_omada_config()` to accept either `AppSettings` or `OmadaConfig` DB model as source; when given `OmadaConfig`, decrypt `encrypted_password` via `decrypt_credential()` to get plaintext for the config dict; keep backward compatibility with `AppSettings` for migration phase
- [ ] T011 [US1] Update admin app lifespan in `addon/src/captive_portal/app.py` — after `init_db()`, load `OmadaConfig(id=1)` from DB; if record exists and `omada_configured`, call `build_omada_config()` with DB model to populate `app.state.omada_config`; fall back to `AppSettings`-based config if no DB record (migration hasn't run yet)
- [ ] T012 [US1] Add "Omada" navigation link to ALL existing admin templates — update nav bar in `addon/src/captive_portal/web/templates/admin/dashboard.html`, `grants_enhanced.html`, `integrations.html`, `login.html`, `portal_settings.html`, `vouchers.html` to include `<a href="{{ rp }}/admin/omada-settings/" class="nav-link">Omada</a>` between "Integrations" and "Settings" links

**Verification**: Run `uv run pytest tests/unit/models/test_omada_config_model.py tests/integration/test_omada_settings_ui.py -v` — all tests pass. Run `uv run pytest tests/ -x -q` — full suite passes (no regressions). Manually verify: start app, navigate to `/admin/omada-settings/`, fill form, save, confirm flash message, return to page and verify values persisted (password masked).

**Checkpoint**: User Story 1 is fully functional — admin can manage Omada controller settings via web UI.

---

## Phase 4: User Story 2 — Automatic Migration of Existing YAML Settings (Priority: P2)

**Goal**: On first startup after upgrade, the system reads existing YAML/env settings and migrates them into the database (encrypting the Omada password). Migration is idempotent — runs only once per setting category.

**Independent Test**: Configure settings in YAML/env, start the app, verify all settings appear correctly in the DB and web UI. Restart and verify migration does not overwrite DB values.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T013 [P] [US2] Write unit tests for config migration service in `tests/unit/services/test_config_migration.py` — cover: full migration from AppSettings with all fields populated (Omada encrypted, session/guest copied); idempotency (existing OmadaConfig row → skip Omada migration); idempotency (non-default PortalConfig.session_idle_minutes → skip session migration); partial migration (only Omada configured, no session settings); migration with empty/default AppSettings (all defaults applied); password encryption during migration; MigrationResult fields populated correctly
- [ ] T014 [P] [US2] Write integration test for end-to-end migration flow in `tests/integration/test_config_migration_e2e.py` — cover: simulate full startup with YAML values → verify DB records created → verify web UI shows migrated values; simulate restart → verify migration skipped → DB values unchanged; simulate fresh install (no YAML, no DB) → verify defaults applied

### Implementation for User Story 2

- [ ] T015 [US2] Create the startup migration service in `addon/src/captive_portal/services/config_migration.py` — implement:
  - `MigrationResult` Pydantic model with fields: `omada_migrated: bool`, `session_fields_migrated: int`, `guest_url_migrated: bool`, `skipped_reason: str | None`
  - `async def migrate_yaml_to_db(settings: AppSettings, session: Session, key_path: str = "/data/.omada_key") -> MigrationResult`:
    1. **Omada migration**: If no `OmadaConfig(id=1)` in DB AND `settings.omada_configured` is True → create `OmadaConfig` record with `controller_url`, `username`, `encrypted_password` (encrypt via `encrypt_credential(settings.omada_password)`), `site_name`, `controller_id`, `verify_ssl` from AppSettings
    2. **Session migration**: If `PortalConfig(id=1)` exists and `session_idle_minutes == 30` (default) AND `settings.session_idle_minutes != 30` → update; same logic for `session_max_hours` (default 8)
    3. **Guest URL migration**: If `PortalConfig.guest_external_url == ""` AND `settings.guest_external_url != ""` → update
    4. Log all migrated values (redact password), return MigrationResult
- [ ] T016 [US2] Wire migration into admin app lifespan in `addon/src/captive_portal/app.py` — after `init_db()` and before Omada config build, call `migrate_yaml_to_db(settings, db_session)`, log the `MigrationResult`; then load `OmadaConfig` from DB for Omada config build (replaces direct AppSettings usage)
- [ ] T017 [US2] Wire migration into guest app lifespan in `addon/src/captive_portal/guest_app.py` — after `init_db()`, load `OmadaConfig(id=1)` from DB; if `omada_configured`, call `build_omada_config()` with DB model to set `app.state.omada_config`; load `PortalConfig` for `guest_external_url` from DB instead of AppSettings

**Verification**: Run `uv run pytest tests/unit/services/test_config_migration.py tests/integration/test_config_migration_e2e.py -v` — all tests pass. Run `uv run pytest tests/ -x -q` — full suite passes. Verify: set env vars for Omada settings, start app, check DB has `omada_config` record with encrypted password, restart, confirm no re-migration.

**Checkpoint**: User Story 2 is fully functional — existing YAML settings automatically migrate to DB on upgrade.

---

## Phase 5: User Story 3 — Configure Session and Guest Portal Settings via Web UI (Priority: P3)

**Goal**: Admin can adjust session idle timeout, session max duration, and guest external URL on the existing Settings page. Changes take effect immediately without restart.

**Independent Test**: Navigate to `/admin/portal-settings/`, modify session timeout and guest URL fields, save, verify values persisted and new sessions use updated values.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T018 [P] [US3] Write integration tests for extended portal settings in `tests/integration/test_portal_settings_extended.py` — cover: GET renders new session/guest fields with current values; POST saves valid session_idle_minutes (1-1440) and session_max_hours (1-168); POST saves valid guest_external_url; POST rejects invalid session_idle_minutes (0, -1, 1441); POST rejects invalid session_max_hours (0, 169); POST rejects invalid guest_external_url (not http/https); POST with empty guest_external_url saves empty string; POST logs audit with new fields in metadata; session config is reloaded after save

### Implementation for User Story 3

- [ ] T019 [US3] Extend the portal settings page with session and guest URL fields — all of the following in one task:
  - **Model**: Add `session_idle_minutes: int = Field(default=30, ge=1, le=1440)`, `session_max_hours: int = Field(default=8, ge=1, le=168)`, `guest_external_url: str = Field(default="", max_length=2048)` to `PortalConfig` in `addon/src/captive_portal/models/portal_config.py`
  - **Route GET**: Update `get_portal_settings()` in `addon/src/captive_portal/api/routes/portal_settings_ui.py` — no changes needed (config object already passed to template, new fields auto-available)
  - **Route POST**: Update `update_portal_settings()` in `addon/src/captive_portal/api/routes/portal_settings_ui.py` — add form params: `session_idle_minutes: int`, `session_max_hours: int`, `guest_external_url: str = ""`; validate ranges (1-1440, 1-168); validate guest URL format (http/https or empty, no query/fragment); persist new fields to `PortalConfig`; update audit log metadata to include new fields
  - **Template**: Update `addon/src/captive_portal/web/templates/admin/portal_settings.html` — add "Session Timeouts" section with `session_idle_minutes` (number input, min=1, max=1440, label "Session Idle Timeout (minutes)") and `session_max_hours` (number input, min=1, max=168, label "Session Max Duration (hours)"); add "Guest Portal" section with `guest_external_url` (url input, label "Guest External URL", placeholder "https://guest.example.com"); place new sections after existing form sections but before submit button
  - **JS validation**: Update `addon/src/captive_portal/web/themes/default/admin-portal-settings.js` — add validation for `session_idle_minutes` (1-1440), `session_max_hours` (1-168), `guest_external_url` (valid URL or empty)
  - **Session reload**: After saving in POST handler, rebuild `SessionConfig` from updated `PortalConfig` and store in `app.state.session_config` (if session_config is used from app.state); also update `app.state.guest_external_url` if applicable

**Verification**: Run `uv run pytest tests/integration/test_portal_settings_extended.py -v` — all tests pass. Run `uv run pytest tests/ -x -q` — full suite passes (including existing portal settings tests). Manually verify: navigate to Settings page, change session idle timeout to 45 min, save, confirm flash message, return to page and verify 45 is shown.

**Checkpoint**: User Story 3 is fully functional — admin can manage session timeouts and guest URL via web UI.

---

## Phase 6: User Story 4 — YAML Config Simplified to Startup-Only Settings (Priority: P4)

**Goal**: Clean up the YAML schema to only 4 startup-only settings, remove migrated env var exports from s6 run scripts, and update settings resolution to read migrated settings from DB.

**Independent Test**: Inspect `addon/config.yaml` — only `log_level`, `ha_base_url`, `ha_token`, `debug_guest_portal` remain. Start addon, verify it functions using DB-backed settings for Omada/session/guest URL.

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T020 [P] [US4] Update existing settings tests in `tests/unit/config/test_settings_load.py`, `tests/unit/config/test_settings_omada_fields.py`, `tests/unit/config/test_settings_precedence.py`, and `tests/unit/config/test_settings_guest.py` — remove or update tests for migrated fields that are no longer resolved by `AppSettings.load()`; add tests verifying that `AppSettings` only resolves Category A fields (log_level, db_path, ha_base_url, ha_token, debug_guest_portal); verify that `log_effective()` no longer logs migrated fields; verify `to_session_config()` and `omada_configured` are removed or updated

### Implementation for User Story 4

- [ ] T021 [US4] Simplify `addon/config.yaml` schema — remove these entries from the `schema:` block: `session_idle_timeout`, `session_max_duration`, `guest_external_url`, `omada_controller_url`, `omada_username`, `omada_password`, `omada_site_name`, `omada_controller_id`, `omada_verify_ssl`; retain only: `log_level`, `ha_base_url`, `ha_token`, `debug_guest_portal`
- [ ] T022 [US4] Simplify s6 run scripts — in `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run`: remove all `CP_OMADA_*` env var exports (CP_OMADA_CONTROLLER_URL, CP_OMADA_USERNAME, CP_OMADA_PASSWORD, CP_OMADA_SITE_NAME, CP_OMADA_CONTROLLER_ID, CP_OMADA_VERIFY_SSL); keep CP_DEBUG_GUEST_PORTAL export. In `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/run`: remove CP_GUEST_EXTERNAL_URL and all `CP_OMADA_*` env var exports; keep CP_DEBUG_GUEST_PORTAL export
- [ ] T023 [US4] Simplify `AppSettings` in `addon/src/captive_portal/config/settings.py` — remove migrated fields from class definition (session_idle_minutes, session_max_hours, guest_external_url, omada_controller_url, omada_username, omada_password, omada_site_name, omada_controller_id, omada_verify_ssl); remove their entries from `_ADDON_OPTION_MAP`, `_ENV_VAR_MAP`, `_FIELD_VALIDATORS`, and the `load()` resolution loop; remove `omada_configured` property, `to_session_config()` method; update `log_effective()` to only log Category A fields; **keep Category B fields temporarily accessible for migration reads** by retaining them in a separate `_load_for_migration()` classmethod that reads YAML values without storing them as class fields — or keep them on the class but mark them as deprecated and only used by `migrate_yaml_to_db()`
- [ ] T024 [US4] Update all files that import migrated fields from `AppSettings` — grep for `settings.omada_`, `settings.session_idle_minutes`, `settings.session_max_hours`, `settings.guest_external_url`, `settings.omada_configured`, `settings.to_session_config()` across `addon/src/` and redirect them to read from DB models (`OmadaConfig`, `PortalConfig`); update `addon/src/captive_portal/app.py` and `addon/src/captive_portal/guest_app.py` accordingly

**Verification**: Run `uv run pytest tests/ -x -q` — full suite passes. Run `uv run ruff check addon/src/ tests/` — no lint errors. Run `uv run mypy addon/src/` — no type errors. Verify `addon/config.yaml` has exactly 4 schema entries. Verify `grep "CP_OMADA" addon/rootfs/etc/s6-overlay/s6-rc.d/*/run` returns no matches. Verify `grep "CP_GUEST_EXTERNAL_URL" addon/rootfs/etc/s6-overlay/s6-rc.d/*/run` returns no matches.

**Checkpoint**: User Story 4 is complete — YAML schema is clean, s6 scripts simplified, settings resolution uses DB.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and cross-cutting quality checks.

- [ ] T025 [P] Extend existing API response/update models for portal config in `addon/src/captive_portal/api/routes/portal_config.py` — add `session_idle_minutes`, `session_max_hours`, `guest_external_url` to `PortalConfigResponse` and `PortalConfigUpdate` Pydantic models; update GET/PUT handlers to include new fields
- [ ] T026 [P] Run full test suite and fix any regressions — execute `uv run pytest tests/ -x -v --tb=long` and ensure all 1390+ existing tests plus new tests pass; fix any failures caused by removed AppSettings fields or changed signatures
- [ ] T027 [P] Run linting and type checking — execute `uv run ruff check addon/src/ tests/` and `uv run mypy addon/src/`; fix all errors; ensure all new files have SPDX headers (`SPDX-FileCopyrightText: 2026 Andrew Grimberg` and `SPDX-License-Identifier: Apache-2.0`)
- [ ] T028 Run quickstart.md validation — follow the steps in `specs/012-yaml-to-webui-config/quickstart.md` end-to-end: install deps, run tests, verify all four implementation phases work as described
- [ ] T029 Update REUSE.toml if needed — ensure any new files are covered by the REUSE licensing configuration

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on T008 (OmadaConfig model must exist before registering in database.py)
- **User Story 1 (Phase 3)**: Depends on Phase 1 (encryption) + Phase 2 (DB registration) + T008 (model)
- **User Story 2 (Phase 4)**: Depends on Phase 1 (encryption) + Phase 2 (DB registration) + Phase 3 (OmadaConfig model, routes)
- **User Story 3 (Phase 5)**: Depends on Phase 2 (DB migration for portal_config columns)
- **User Story 4 (Phase 6)**: Depends on Phase 3 + Phase 4 + Phase 5 (all DB-backed settings must be in place before removing YAML)
- **Polish (Phase 7)**: Depends on all prior phases

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — core MVP, no other story dependencies
- **User Story 2 (P2)**: Depends on User Story 1 (needs OmadaConfig model and route wiring to exist)
- **User Story 3 (P3)**: Can start after Phase 2 — **independent of US1 and US2** (only extends PortalConfig)
- **User Story 4 (P4)**: Depends on US1 + US2 + US3 all being complete (cleanup requires all DB paths working)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before routes/services
- Routes include template + JS + validation (full vertical slice)
- Core implementation before integration wiring
- Story complete before moving to next priority

### Parallel Opportunities

- T002 + T003 can run in parallel (different files)
- T006 + T007 can run in parallel (different test files)
- T013 + T014 can run in parallel (different test files)
- US1 and US3 can theoretically run in parallel after Phase 2 (different models, different pages)
- T025 + T026 + T027 can run in parallel (different concerns)

---

## Parallel Example: User Story 1

```bash
# Launch both test files for User Story 1 together:
Task: "Write unit tests for OmadaConfig model in tests/unit/models/test_omada_config_model.py"
Task: "Write integration tests for Omada settings UI in tests/integration/test_omada_settings_ui.py"

# After tests written, implement model first, then full page:
Task: "Create OmadaConfig SQLModel in addon/src/captive_portal/models/omada_config.py"
Task: "Create the complete Omada settings page (route + template + JS + register)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (encryption module + dependency)
2. Complete Phase 2: Foundational (DB registration + migrations)
3. Complete Phase 3: User Story 1 (Omada settings page)
4. **STOP and VALIDATE**: Test Omada settings page independently
5. Deploy/demo if ready — admin can manage Omada settings via web UI

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Omada settings via web UI (MVP!)
3. Add User Story 2 → Existing YAML settings auto-migrate on upgrade
4. Add User Story 3 → Session/guest settings on portal settings page
5. Add User Story 4 → YAML cleanup, s6 script simplification
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Omada page)
   - Developer B: User Story 3 (Portal settings extension) — independent of US1
3. After US1 complete:
   - Developer A: User Story 2 (Migration service)
4. After US1 + US2 + US3 complete:
   - Either developer: User Story 4 (YAML cleanup)

---

## Summary

| Metric | Value |
|--------|-------|
| **Total tasks** | 29 |
| **Phase 1 (Setup)** | 3 tasks |
| **Phase 2 (Foundational)** | 2 tasks |
| **Phase 3 (US1 — Omada Page)** | 7 tasks |
| **Phase 4 (US2 — Migration)** | 5 tasks |
| **Phase 5 (US3 — Session/Guest)** | 2 tasks |
| **Phase 6 (US4 — YAML Cleanup)** | 5 tasks |
| **Phase 7 (Polish)** | 5 tasks |
| **Parallel opportunities** | 12 tasks marked [P] |
| **Suggested MVP scope** | Phases 1-3 (User Story 1) |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing
- Commit after each task with DCO sign-off (`git commit -s`)
- Stop at any checkpoint to validate story independently
- All new files MUST have SPDX headers
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
