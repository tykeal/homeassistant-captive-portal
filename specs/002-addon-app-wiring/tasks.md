SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Wire Real Application into Addon Container

**Input**: Design documents from `/specs/002-addon-app-wiring/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Included — TDD is non-negotiable per project constitution. Tests are written first (red), then implementation (green).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the configuration module package structure needed by all subsequent phases

- [ ] T001 Create config package `src/captive_portal/config/__init__.py` with SPDX header, module docstring, and placeholder `AppSettings` re-export comment

---

## Phase 2: Foundational (Configuration Layer)

**Purpose**: Implement `AppSettings` configuration model with three-tier precedence (addon options → env vars → defaults) and database engine disposal. This is the core infrastructure that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (TDD Red — write first, must fail)

- [ ] T002 [P] Activate skipped tests in `tests/unit/config/test_settings_load.py` — remove `pytest.skip("Config module not implemented yet")`, update assertions to match `AppSettings` interface: defaults loading (`log_level="info"`, `db_path="/data/captive_portal.db"`, `session_idle_minutes=30`, `session_max_hours=8`), environment variable override via `CP_` prefix, validation error on invalid values (e.g. negative timeout, unknown log level), secret redaction in string representation, and database path default
- [ ] T003 [P] Create `tests/unit/config/test_addon_options_loader.py` with SPDX header — test valid `/data/options.json` parsing with all three addon fields (`log_level`, `session_idle_timeout`, `session_max_duration`), missing file graceful fallback to defaults, invalid option values (wrong type, out of range) ignored with warning logged, and partial options (only some fields present) merged correctly with defaults for missing fields
- [ ] T004 [P] Create `tests/unit/config/test_settings_precedence.py` with SPDX header — test three-tier precedence per FR-009: addon option overrides env var overrides default; invalid addon value for one field falls through to `CP_`-prefixed env var while other valid addon values are kept; invalid addon value with no env var falls through to built-in default; test all four fields (`log_level`, `db_path`, `session_idle_minutes`, `session_max_hours`) independently

### Implementation (TDD Green)

- [ ] T005 Implement `AppSettings` pydantic `BaseModel` in `src/captive_portal/config/settings.py` with SPDX header — fields: `log_level` (str, default `"info"`, env `CP_LOG_LEVEL`, valid: trace/debug/info/notice/warning/error/fatal), `db_path` (str, default `"/data/captive_portal.db"`, env `CP_DB_PATH`), `session_idle_minutes` (int, default `30`, env `CP_SESSION_IDLE_TIMEOUT`, min 1), `session_max_hours` (int, default `8`, env `CP_SESSION_MAX_DURATION`, min 1); classmethod `load(options_path="/data/options.json")` with per-field three-tier precedence and warning logging for each invalid addon value; methods `to_session_config() -> SessionConfig`, `to_log_config() -> dict` with HA-to-Python log level mapping (trace/debug→DEBUG, info/notice→INFO, warning→WARNING, error→ERROR, fatal→CRITICAL), `log_effective(logger) -> None` logging all effective settings at INFO excluding secrets; update `src/captive_portal/config/__init__.py` to export `AppSettings`
- [ ] T006 Add `dispose_engine()` function to `src/captive_portal/persistence/database.py` — calls `_engine.dispose()` on the module-level engine to close all pooled SQLAlchemy connections; returns `None`; is a safe no-op with a debug log message when engine has not been created yet

**Checkpoint**: Configuration layer complete — `AppSettings.load()` works with addon options, env vars, and defaults. All Phase 2 tests pass (green). User story implementation can now begin.

---

## Phase 3: User Story 1 — Addon Starts the Real Application (Priority: P1) 🎯 MVP

**Goal**: Replace the placeholder startup so the addon launches the full captive portal application with all 12 routers, 8 database models, middleware, authentication, and the admin UI on port 8080.

**Independent Test**: Install the addon, start it, confirm: (1) `/api/ready` returns success with database check, (2) admin login page loads, (3) guest portal page loads, (4) data persists across restarts.

### Tests for User Story 1 (TDD Red)

- [ ] T007 [P] [US1] Create `tests/integration/test_addon_startup_wiring.py` with SPDX header — test `create_app(settings)` with explicit `AppSettings`: database tables created on startup, `/api/health` returns 200, `/api/ready` returns 200 with database check passing, guest portal route responds (not 404), admin route responds (not 404), all existing route prefixes still registered (FR-014); test `create_app()` without arguments uses `AppSettings.load()` defaults preserving backward compatibility with existing tests
- [ ] T008 [P] [US1] Create `tests/unit/routes/test_template_resolution.py` with SPDX header (create `tests/unit/routes/__init__.py` if needed) — test that `_TEMPLATES_DIR` variable in `guest_portal.py`, `portal_settings_ui.py`, and `integrations_ui.py` each resolves to an existing directory containing expected template subdirectories (`guest/`, `admin/`, `portal/`) regardless of current working directory

### Implementation for User Story 1

- [ ] T009 [US1] Modify `src/captive_portal/app.py` — update `create_app()` signature to `create_app(settings: AppSettings | None = None) -> FastAPI`; when `settings` is `None` call `AppSettings.load()`; replace direct `SessionConfig()` construction with `settings.to_session_config()`; add `@asynccontextmanager` lifespan handler: on startup configure logging via `settings.to_log_config()`, log effective config via `settings.log_effective()`, call `create_db_engine(f"sqlite:///{settings.db_path}")` and `init_db(engine)` for automatic table creation (FR-004); on shutdown call `dispose_engine()`; mount `StaticFiles(directory=<package-relative web/themes/>)` at `/static/themes`; pass lifespan to `FastAPI()` constructor
- [ ] T010 [P] [US1] Fix template path resolution in `src/captive_portal/api/routes/guest_portal.py` — replace hardcoded `Jinja2Templates(directory="src/captive_portal/web/templates")` with package-relative path: `_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"` and `templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))`; preserve existing `templates.env.autoescape = True` setting
- [ ] T011 [P] [US1] Fix template path resolution in `src/captive_portal/api/routes/portal_settings_ui.py` — replace hardcoded `Jinja2Templates(directory="src/captive_portal/web/templates")` with package-relative path: `_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"` and `templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))`
- [ ] T012 [P] [US1] Fix template path resolution in `src/captive_portal/api/routes/integrations_ui.py` — replace hardcoded `Jinja2Templates(directory="src/captive_portal/web/templates")` with package-relative path: `_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"` and `templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))`
- [ ] T013 [US1] Update `addon/Dockerfile` — add `COPY pyproject.toml /app/` and `COPY src/ /app/src/` before pip install step; replace `"$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir fastapi uvicorn[standard]` with `"$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir /app` to install the full `captive_portal` package with all dependencies from `pyproject.toml`; keep existing `ARG BUILD_FROM`, `apk add` packages, venv setup, `EXPOSE 8080`, and `CMD`
- [ ] T014 [US1] Replace placeholder in `addon/rootfs/usr/bin/run.sh` — remove the inline Python placeholder app; exec uvicorn with the real application factory: `exec "$VIRTUAL_ENV/bin/python" -m uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080`; keep the shebang and any existing bashio sourcing for HA log integration
- [ ] T015 [US1] Run full existing test suite to verify zero regressions from addon wiring changes (FR-015) — execute `uv run pytest tests/` from repository root and confirm all previously passing tests still pass with no new failures

**Checkpoint**: The addon starts the full application with database initialization, serves all 12 route groups, templates render via package-relative paths, and static themes are served. This is the **MVP** — User Story 1 is independently functional and testable.

---

## Phase 4: User Story 2 — Administrator Configures the Addon (Priority: P2)

**Goal**: Expose `log_level`, `session_idle_timeout`, and `session_max_duration` options in the HA addon configuration panel so administrators can tune addon behavior through the standard HA UI without editing files.

**Independent Test**: Open addon configuration tab in HA UI, change log level to "debug" and session timeout to 15, restart addon, confirm debug logs appear and sessions expire at 15 minutes.

### Tests for User Story 2 (TDD Red)

- [ ] T016 [P] [US2] Create `tests/integration/test_addon_config_application.py` with SPDX header — test `AppSettings.load()` with a mock `/data/options.json` containing `{"log_level": "debug", "session_idle_timeout": 15, "session_max_duration": 4}` produces `AppSettings` with `log_level="debug"`, `session_idle_minutes=15`, `session_max_hours=4`; test `create_app()` with debug-level settings produces debug-level log output; test empty options `{}` results in all defaults (`info`, `30`, `8`); test that `to_session_config()` returns `SessionConfig(idle_minutes=15, max_hours=4)` matching the loaded options

### Implementation for User Story 2

- [ ] T017 [US2] Update `addon/config.json` — replace empty `"schema": {}` with HA addon schema format matching `contracts/addon-options-schema.json`: `"log_level": "list(trace|debug|info|notice|warning|error|fatal)?"` defaulting to `"info"`, `"session_idle_timeout": "int(1,)?"` defaulting to `30`, `"session_max_duration": "int(1,)?"` defaulting to `8`; the `?` suffix marks each option as optional so the addon starts with defaults when no configuration is provided

**Checkpoint**: User Stories 1 AND 2 are both independently functional. Configuration options appear in the HA addon panel, and changes take effect after addon restart.

---

## Phase 5: User Story 3 — Guest Portal Pages Render Correctly (Priority: P2)

**Goal**: Confirm all guest-facing and admin HTML pages render with proper styling and no missing assets (CSS, images) when served from the addon container.

**Independent Test**: Navigate to guest portal authorization page, confirm styled HTML with booking code form loads; check browser network tab for zero 404 errors on CSS/static resources.

### Tests for User Story 3 (TDD Red)

- [ ] T018 [P] [US3] Create `tests/integration/test_guest_portal_full_rendering.py` with SPDX header — test guest pages via TestClient: authorization page returns 200 with HTML containing form elements, welcome page returns 200 with HTML, error page returns 200 with HTML; test admin pages: portal settings page returns 200 with HTML; test static assets: `GET /static/themes/default/admin.css` returns 200 with CSS content-type; test no broken asset references by parsing HTML responses for `<link>` and `<script>` tags and requesting each referenced URL

### Implementation for User Story 3

- [ ] T019 [US3] Verify and update CSS/static asset URL references in all 9 HTML templates under `src/captive_portal/web/templates/` — ensure every `<link href="...">`, `<script src="...">`, and `<img src="...">` tag uses the `/static/themes/` URL prefix matching the `StaticFiles` mount point configured in `app.py`; check templates in `admin/` (dashboard.html, grants_enhanced.html, integrations.html, portal_settings.html), `guest/` (authorize.html, booking_authorize.html, error.html, welcome.html), and `portal/` (index.html)

**Checkpoint**: User Stories 1-3 are all independently functional. Guest portal fully renders with proper styling and zero 404 errors for static assets.

---

## Phase 6: User Story 4 — Application Graceful Shutdown (Priority: P3)

**Goal**: When the addon is stopped or restarted, close database connections cleanly and finish in-flight requests so no data corruption occurs.

**Independent Test**: Stop the addon while requests are being processed; restart and verify all previously committed data is intact and database is not corrupted.

### Tests for User Story 4 (TDD Red)

- [ ] T020 [P] [US4] Create `tests/integration/test_graceful_shutdown.py` with SPDX header — test that app shutdown (via lifespan exit) calls `dispose_engine()` and closes database connections; test that the database file is not locked after shutdown and a new engine can open it; test that data committed before shutdown is fully intact when a new app instance starts (no corruption from incomplete WAL checkpoint)
- [ ] T021 [P] [US4] Create `tests/unit/persistence/test_dispose_engine.py` with SPDX header (create `tests/unit/persistence/__init__.py` if needed) — test `dispose_engine()` successfully closes all pooled connections on an active engine; test `dispose_engine()` is a safe no-op when no engine has been created (no exception raised); test a new engine can be created and used normally after `dispose_engine()` is called

**Checkpoint**: All user stories 1-4 independently functional. Application shuts down cleanly within 10 seconds (SC-008) with no database corruption.

---

## Phase 7: User Story 5 — Multi-Architecture Support (Priority: P3)

**Goal**: The addon Docker image builds and runs correctly on both amd64 and aarch64 architectures.

**Independent Test**: Build the Docker image targeting each architecture and confirm the application starts and serves requests on both.

### Implementation for User Story 5

- [ ] T022 [US5] Verify `addon/Dockerfile` multi-arch compatibility — confirm `ARG BUILD_FROM` is preserved as the build argument for base image selection (amd64 vs aarch64), no architecture-specific `apk` packages were added beyond what was already present, `pip install /app` works with Alpine Python on both architectures; review `pyproject.toml` dependencies for any packages requiring architecture-specific compilation (argon2-cffi needs C compiler — confirm `apk add` includes build tools or pre-built wheels are available)
- [ ] T023 [US5] Update `tests/integration/test_addon_build_run.py` — replace any placeholder validation assertions (e.g., checking for `"placeholder"` or `"not yet wired"` text in responses) with real application validation: assert `GET /api/health` returns 200 with `{"status": "ok"}`, assert `GET /api/ready` returns 200, assert response body does not contain `"placeholder"` text

**Checkpoint**: All user stories 1-5 independently functional. Addon builds and runs on both amd64 and aarch64 architectures (SC-007).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling, startup logging verification, documentation, and final end-to-end validation across all user stories

- [ ] T024 [P] Create `tests/unit/config/test_startup_logging.py` with SPDX header — test `AppSettings.log_effective()` logs all four settings (`log_level`, `db_path`, `session_idle_minutes`, `session_max_hours`) at INFO level; test no secret or sensitive values appear in log output; test log output includes both field names and their effective values (FR-016)
- [ ] T025 [P] Create `tests/unit/config/test_data_dir_errors.py` with SPDX header — test clear error message when `db_path` parent directory does not exist; test clear error message when `db_path` parent directory is not writable; test application fails fast with descriptive error (not silent hang) on database initialization failure
- [ ] T026 [P] Add data directory validation in `src/captive_portal/config/settings.py` `load()` method — after resolving effective `db_path`, validate that the parent directory exists and is writable; raise a descriptive `RuntimeError` with the path and permission details if validation fails (edge case from spec)
- [ ] T027 [P] Update project documentation in `docs/` or `README.md` — add addon configuration reference documenting available config options (`log_level`, `session_idle_timeout`, `session_max_duration`), corresponding environment variables (`CP_LOG_LEVEL`, `CP_DB_PATH`, `CP_SESSION_IDLE_TIMEOUT`, `CP_SESSION_MAX_DURATION`), default values, and precedence rules per quickstart.md
- [ ] T028 Run `specs/002-addon-app-wiring/quickstart.md` end-to-end validation — execute the verification steps: build Docker image locally, start container with port 8080, `curl /api/health` returns OK, `curl /api/ready` returns OK with database check, configure via environment variables and verify changes take effect

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) completion — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **US2 (Phase 4)**: Depends on Foundational (Phase 2) completion; can run in parallel with US1
- **US3 (Phase 5)**: Depends on US1 (Phase 3) — template path fixes and static file mount must be in place
- **US4 (Phase 6)**: Depends on Foundational (Phase 2) — `dispose_engine()` must exist; tests validate lifespan handler from US1
- **US5 (Phase 7)**: Depends on US1 (Phase 3) — Dockerfile must be updated before multi-arch validation
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — no dependencies on other stories (**critical path, start here**)
- **US2 (P2)**: After Foundational — independent of US1 (`AppSettings.load()` already reads `/data/options.json`); sequentially after US1 if single developer
- **US3 (P2)**: After US1 — depends on template path fixes (T010-T012) and `StaticFiles` mount (T009)
- **US4 (P3)**: After Foundational — depends on `dispose_engine()` (T006); tests exercise lifespan from US1 (T009)
- **US5 (P3)**: After US1 — depends on updated Dockerfile (T013) and run.sh (T014)

### Within Each User Story

1. Tests MUST be written and FAIL before implementation (TDD Red)
2. Template/model/config changes before integration/container changes
3. Core Python implementation before Dockerfile/run.sh changes
4. All story tests MUST pass after implementation (TDD Green)
5. Commit after each task or logical group (atomic commits per constitution)

### Parallel Opportunities

- **Phase 2 Tests**: T002, T003, T004 can all run in parallel (different test files)
- **Phase 3 Tests**: T007, T008 can run in parallel (different test files)
- **Phase 3 Template Fixes**: T010, T011, T012 can all run in parallel (different route files)
- **Cross-Story**: US2 and US4 can start in parallel after Foundational phase (if team capacity allows)
- **Phase 8**: T024, T025, T026, T027 can all run in parallel (different files)

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (TDD Red):
Task T007: "Create tests/integration/test_addon_startup_wiring.py"
Task T008: "Create tests/unit/routes/test_template_resolution.py"

# Launch all US1 template fixes together:
Task T010: "Fix template path in src/captive_portal/api/routes/guest_portal.py"
Task T011: "Fix template path in src/captive_portal/api/routes/portal_settings_ui.py"
Task T012: "Fix template path in src/captive_portal/api/routes/integrations_ui.py"
```

## Parallel Example: Foundational Phase

```bash
# Launch all Foundational tests together (TDD Red):
Task T002: "Activate tests in tests/unit/config/test_settings_load.py"
Task T003: "Create tests/unit/config/test_addon_options_loader.py"
Task T004: "Create tests/unit/config/test_settings_precedence.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T006)
3. Complete Phase 3: User Story 1 (T007–T015)
4. **STOP and VALIDATE**: Addon starts real app, `/api/ready` works, templates render, data persists
5. Deploy/demo if ready — the addon is now functional

### Incremental Delivery

1. Setup + Foundational → Configuration layer ready
2. Add US1 → Real app starts in addon container → **Deploy/Demo (MVP!)**
3. Add US2 → HA UI configuration options work → Deploy/Demo
4. Add US3 → Guest portal fully styled, no 404s → Deploy/Demo
5. Add US4 → Graceful shutdown verified, no corruption → Deploy/Demo
6. Add US5 → Multi-arch builds verified → Deploy/Demo
7. Polish → Edge cases, docs, quickstart validation → Final release

### Parallel Team Strategy

With multiple developers after Foundational is complete:

- **Developer A**: US1 (P1 — critical path, MVP)
- **Developer B**: US2 (P2 — config.json schema, independent of US1)
- **Developer C**: US4 (P3 — shutdown tests, independent of US1)
- After US1 completes: US3 and US5 can proceed (depend on US1 outputs)

---

## Notes

- All new files MUST include SPDX header: `SPDX-FileCopyrightText: 2026 Andrew Grimberg` / `SPDX-License-Identifier: Apache-2.0`
- Existing files being modified retain their existing SPDX headers (including the current copyright year), unless there is an intentional project-wide update
- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD is non-negotiable per constitution: tests fail (red) before implementation (green)
- Commit after each task or logical group (atomic commits per constitution principle V)
- Existing test suite MUST continue passing after every task (FR-015)
- New test directories (`tests/unit/routes/`, `tests/unit/persistence/`) need `__init__.py` files
