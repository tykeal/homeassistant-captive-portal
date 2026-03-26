SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Dual-Port Networking

**Input**: Design documents from `/specs/004-dual-port-networking/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/guest-api.md, quickstart.md

**Tests**: TDD is a NON-NEGOTIABLE constitutional principle for this project. Tests are written FIRST (RED), implementation makes them pass (GREEN), then refactor.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Addon infrastructure**: `addon/rootfs/etc/s6-overlay/s6-rc.d/`
- **Addon config**: `addon/config.yaml`, `addon/Dockerfile`
- **Tests**: `tests/unit/`, `tests/integration/`
- **SPDX Headers**: All new files MUST include `SPDX-FileCopyrightText: 2026 Andrew Grimberg` and `SPDX-License-Identifier: Apache-2.0`

---

## Phase 1: Setup (s6-overlay Infrastructure & Addon Config)

**Purpose**: Create the s6-overlay service definitions, addon configuration, and Dockerfile changes needed to run the guest listener as an independent process.

- [ ] T001 [P] Create s6-overlay service files for captive-portal-guest under addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/
  - Create `type` file containing `longrun`
  - Create `run` script using `#!/command/with-contenv bashio` shebang (reference existing `captive-portal/run` and rentalsync-bridge patterns):
    - Add SPDX header (year 2026) and `# shellcheck shell=bash`
    - Use `bashio::config 'guest_external_url' ''` to read external URL from addon options
    - Export as `CP_GUEST_EXTERNAL_URL` environment variable
    - Log startup info via `bashio::log.info`
    - `exec python -m uvicorn captive_portal.guest_app:create_guest_app --factory --host 0.0.0.0 --port 8099` (NO `--root-path` since guest listener is not behind ingress)
  - Create `finish` script matching existing `captive-portal/finish` pattern:
    - Add SPDX header (year 2026) and `# shellcheck shell=bash`
    - Log warning on non-zero/non-256 exit codes
  - Create empty `dependencies.d/` directory (no inter-service dependencies)
  - Create empty registration file `addon/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/captive-portal-guest`

- [ ] T002 [P] Update addon/config.yaml to declare guest port and guest_external_url schema option
  - Add `"8099/tcp": 8099` to `ports:` section (guest portal default host port 8099)
  - Add `"8099/tcp": Guest captive portal (configure WiFi controller to redirect here)` to `ports_description:`
  - Add `guest_external_url: "url?"` to `schema:` section

- [ ] T003 [P] Update addon/Dockerfile to build guest service support
  - Add `RUN chmod +x /etc/s6-overlay/s6-rc.d/captive-portal-guest/run` after existing chmod line
  - Add `EXPOSE 8099` after existing `EXPOSE 8080`

**Checkpoint**: s6-overlay infrastructure is ready. Both services will be started by s6-overlay on addon boot. Config schema accepts `guest_external_url`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Python infrastructure that MUST be complete before ANY user story can be implemented — settings model, middleware parameterization, and guest app factory.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Write unit tests for guest_external_url settings and port conflict validation in tests/unit/config/test_settings_guest.py
  - Add SPDX header
  - Test `guest_external_url` field defaults to `""` (empty string)
  - Test loading `guest_external_url` from addon options JSON (`guest_external_url` key)
  - Test loading `guest_external_url` from `CP_GUEST_EXTERNAL_URL` environment variable
  - Test three-tier precedence: addon option > env var > default
  - Test validation: non-empty value must start with `http://` or `https://`
  - Test validation: non-empty value must not end with trailing `/`
  - Test invalid `guest_external_url` falls through to default with warning log
  - Test `log_effective()` includes `guest_external_url` in output
  - Test port conflict: validate that guest port (8099) differs from ingress port (8080) at startup — log a clear error and fail fast if s6 run scripts are misconfigured with the same port
  - All tests should use `AppSettings.load()` with test fixtures (temp options files, env var patching)

- [ ] T005 [P] Parameterize SecurityHeadersMiddleware for configurable frame policy and CSP in addon/src/captive_portal/web/middleware/security_headers.py
  - Add `__init__` method accepting optional `frame_options: str = "SAMEORIGIN"` and `csp: str | None = None` keyword arguments
  - Store parameters as instance attributes
  - In `dispatch()`, use `self.frame_options` for `X-Frame-Options` header (instead of hardcoded `"SAMEORIGIN"`)
  - In `dispatch()`, if `self.csp` is provided, always set/override the `Content-Security-Policy` response header to `self.csp` (even if a route/view has already set CSP)
  - In `dispatch()`, if `self.csp` is not provided (`None`), preserve the existing behavior: only set the default CSP string when the response does not already have a `Content-Security-Policy` header
  - Default behavior (no args) MUST be identical to current behavior — existing tests must not break
  - Guest app will call: `SecurityHeadersMiddleware(frame_options="DENY", csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")`

- [ ] T006 Add guest_external_url field and validation to AppSettings in addon/src/captive_portal/config/settings.py
  - Add `guest_external_url: str = ""` field to `AppSettings` class
  - Add `"guest_external_url": "guest_external_url"` to `_ADDON_OPTION_MAP`
  - Add `"CP_GUEST_EXTERNAL_URL": "guest_external_url"` to `_ENV_VAR_MAP`
  - Add `guest_external_url` to the `_validate_field()` function:
    - Empty string is valid (means "not configured")
    - Non-empty must start with `http://` or `https://`
    - Non-empty must not end with `/`
    - Invalid values logged as warnings, fall through to default
  - Add `_coerce_field` handling for `guest_external_url` (strip whitespace)
  - Add `guest_external_url` to the resolution loop in `load()`
  - Update `log_effective()` to log `guest_external_url` value
  - Run `tests/unit/config/test_settings_guest.py` to verify (should go GREEN)

- [ ] T007 Write unit tests for guest app factory in tests/unit/test_guest_app_factory.py
  - Add SPDX header
  - Test `create_guest_app()` returns a FastAPI instance
  - Test `create_guest_app(settings=AppSettings(db_path=":memory:"))` works with in-memory DB
  - Test guest app mounts these routers (verify routes exist):
    - `captive_detect.router` — `/generate_204`, `/gen_204`, `/connecttest.txt`, `/ncsi.txt`, `/hotspot-detect.html`, `/library/test/success.html`, `/success.txt`
    - `guest_portal.router` — `/guest/authorize`, `/guest/welcome`, `/guest/error`
    - `booking_authorize.router` — `/api/guest/authorize`
    - `health.router` — `/api/health`, `/api/ready`, `/api/live`
  - Test guest app root redirect: `GET /` returns 303 to `/guest/authorize`
  - Test guest app has SecurityHeadersMiddleware (check `X-Frame-Options: DENY` in response headers)
  - Test guest app does NOT have SessionMiddleware (no `session` cookie set on responses)
  - Test guest app stores `guest_external_url` in `app.state`
  - Test static themes mount exists at `/static/themes`
  - Use `TestClient` from `fastapi.testclient` with in-memory DB settings

- [ ] T008 Create guest-only FastAPI app factory in addon/src/captive_portal/guest_app.py
  - Add SPDX header
  - Create `create_guest_app(settings: AppSettings | None = None) -> FastAPI` function
  - If `settings is None`, call `AppSettings.load()`
  - Create lifespan context manager (reuse `_make_lifespan` pattern from `app.py` or inline):
    - Startup: configure logging, validate DB path, create DB engine, init DB
    - Shutdown: dispose engine
  - Create FastAPI instance with title `"Captive Portal Guest Access — Guest Listener"`, no docs (`docs_url=None`, `redoc_url=None`)
  - Store `settings.guest_external_url` in `app.state.guest_external_url`
  - Add SecurityHeadersMiddleware with guest-specific policy:
    - `frame_options="DENY"`
    - `csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"`
  - Do NOT add SessionMiddleware (guest routes don't use admin sessions)
  - Mount static themes: `/static/themes` → `addon/src/captive_portal/web/themes/` directory
  - Register routers (import only these — admin routes are never imported):
    - `from captive_portal.api.routes import captive_detect, guest_portal, booking_authorize, health`
    - `app.include_router(captive_detect.router)`
    - `app.include_router(guest_portal.router)`
    - `app.include_router(booking_authorize.router)`
    - `app.include_router(health.router)`
  - Add root redirect: `GET /` → `303 See Other` to `/guest/authorize`
  - Run `tests/unit/test_guest_app_factory.py` to verify (should go GREEN)

**Checkpoint**: Foundation ready — guest app factory creates a working guest-only FastAPI application with correct routes, middleware, and settings. User story implementation can now begin.

---

## Phase 3: User Story 1 — Guest WiFi Client Reaches Captive Portal (Priority: P1) 🎯 MVP

**Goal**: Guest devices connect to WiFi, get redirected to the captive portal's guest listener, see the authorization page, and complete the authorization flow — all without any Home Assistant authentication prompt.

**Independent Test**: Connect a device to captive WiFi, get redirected to the guest portal URL, and complete authorization without encountering any HA login. Verify using `TestClient(create_guest_app(...))` with captive detection endpoints.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T009 [P] [US1] Write integration tests for captive portal detection on guest listener in tests/integration/test_captive_detect_guest.py
  - Add SPDX header
  - Test ALL seven captive detection URLs on guest app (via `TestClient(create_guest_app(...))`):
    - `GET /generate_204` → 302 redirect to `/guest/authorize`
    - `GET /gen_204` → 302 redirect to `/guest/authorize`
    - `GET /connecttest.txt` → 302 redirect to `/guest/authorize`
    - `GET /ncsi.txt` → 302 redirect to `/guest/authorize`
    - `GET /hotspot-detect.html` → 302 redirect to `/guest/authorize`
    - `GET /library/test/success.html` → 302 redirect to `/guest/authorize`
    - `GET /success.txt` → 302 redirect to `/guest/authorize`
  - Test redirect uses `guest_external_url` when configured:
    - Configure `AppSettings(guest_external_url="http://192.168.1.100:8099", db_path=":memory:")`
    - `GET /generate_204` → Location header: `http://192.168.1.100:8099/guest/authorize`
  - Test redirect uses relative path when `guest_external_url` is empty:
    - Configure `AppSettings(guest_external_url="", db_path=":memory:")`
    - `GET /generate_204` → Location header: `/guest/authorize`
  - Test guest authorization form loads without authentication:
    - `GET /guest/authorize` → 200 OK, HTML content with no HA login form
  - Test `POST /guest/authorize` form submission endpoint exists (returns 303 or 422, not 404)

### Implementation for User Story 1

- [ ] T010 [US1] Update captive detection routes to resolve redirect base from guest_external_url in addon/src/captive_portal/api/routes/captive_detect.py
  - Modify each detection handler to check for `guest_external_url` in `request.app.state`:
    ```python
    guest_url = getattr(request.app.state, "guest_external_url", "")
    if guest_url:
        base = guest_url
    else:
        base = request.scope.get("root_path", "")
    ```
  - Apply to all four handler functions: `android_captive_detect`, `windows_captive_detect`, `apple_captive_detect`, `firefox_captive_detect`
  - Consider extracting a helper `_resolve_redirect_base(request: Request) -> str` to avoid repetition
  - Existing behavior on ingress app is preserved: `request.app.state` has no `guest_external_url`, so `getattr` returns `""`, and `root_path` is used (unchanged)
  - Run `tests/integration/test_captive_detect_guest.py` to verify (should go GREEN)
  - Run `tests/integration/test_captive_portal_detection_redirects.py` to verify existing tests still pass

**Checkpoint**: Guest WiFi clients can be redirected through captive detection endpoints to the guest authorization page on the guest listener. The core captive portal flow works end-to-end. This is the MVP — User Story 1 is fully functional and independently testable.

---

## Phase 4: User Story 2 — Admin UI Continues Working via HA Sidebar (Priority: P2)

**Goal**: Verify the existing admin workflow through Home Assistant ingress is completely unaffected by the dual-port changes. The `create_app()` factory and all ingress routes remain unchanged.

**Independent Test**: Log into Home Assistant, navigate to the captive portal sidebar panel, and perform admin operations. Verify all existing tests pass without modification.

### Verification for User Story 2

- [ ] T011 [US2] Run full existing test suite to verify zero regressions from dual-port changes
  - Run `uv run pytest` (entire test suite) — ALL existing tests must pass
  - Specifically verify these existing test files pass unchanged:
    - `tests/integration/test_root_redirect.py` — root `/` → `/admin/portal-settings/`
    - `tests/integration/test_captive_portal_detection_redirects.py` — detection on ingress app
    - `tests/integration/test_admin_auth_login_logout.py` — admin session auth
    - `tests/integration/test_admin_session_csrf.py` — admin CSRF
    - `tests/integration/test_health_readiness_liveness.py` — health on ingress
    - `tests/integration/test_security_headers.py` — security headers on ingress (still `SAMEORIGIN`)
    - `tests/integration/test_guest_authorization_flow_booking.py` — guest booking on ingress
    - `tests/integration/test_guest_authorization_flow_voucher.py` — guest voucher on ingress
  - Verify `create_app()` in `addon/src/captive_portal/app.py` has NOT been modified (only `captive_detect.py` was changed)
  - Run `uv run ruff check addon/src/captive_portal/app.py` — no lint issues

**Checkpoint**: Backward compatibility confirmed. The admin UI and all ingress functionality work exactly as before.

---

## Phase 5: User Story 3 — Admin Routes Isolated from Guest Port (Priority: P2)

**Goal**: Every admin route returns 404 Not Found (not 401/403) on the guest listener. Admin endpoints are unreachable by design — they are never registered in the guest app's routing table.

**Independent Test**: Send requests for all known admin routes to the guest app's TestClient and confirm each returns 404 Not Found.

### Tests for User Story 3

> **NOTE: These tests should PASS immediately since route isolation was built into the guest app factory (T008). If any fail, the guest app factory is incorrect.**

- [ ] T012 [P] [US3] Write unit tests verifying all admin routes return 404 on guest app in tests/unit/test_guest_app_routes.py
  - Add SPDX header
  - Create `TestClient(create_guest_app(settings=AppSettings(db_path=":memory:")))` fixture
  - Test each admin route returns 404 (not 401, not 403):
    - `GET /admin/portal-settings/` → 404
    - `GET /admin/docs` → 404
    - `GET /admin/redoc` → 404
    - `GET /admin/integrations` → 404
    - `POST /api/admin/auth/login` → 404
    - `GET /api/admin/auth/login` → 404
    - `GET /api/admin/accounts` → 404
    - `GET /api/grants` → 404
    - `GET /api/grants/` → 404
    - `POST /api/vouchers` → 404
    - `GET /api/vouchers` → 404
    - `GET /api/portal/config` → 404
    - `PUT /api/portal/config` → 404
    - `GET /api/audit/config` → 404
    - `GET /api/integrations` → 404
    - `GET /grants` → 404 (placeholder listing endpoint)
  - Verify response bodies do NOT contain authentication-related content (no "login" form, no "unauthorized" message)

- [ ] T013 [P] [US3] Write integration tests for complete dual-port route isolation in tests/integration/test_dual_port_isolation.py
  - Add SPDX header
  - Create both test clients side-by-side:
    - `ingress_client = TestClient(create_app(settings=AppSettings(db_path=":memory:")))`
    - `guest_client = TestClient(create_guest_app(settings=AppSettings(db_path=":memory:")))`
  - For each admin route path, verify:
    - Ingress client: returns non-404 (route exists — may be 200, 302, 401, etc.)
    - Guest client: returns 404 (route does not exist)
  - For each guest route path (`/guest/authorize`, `/generate_204`, `/api/health`), verify:
    - Both clients return non-404 (route exists on both listeners)
  - Test that response from guest client for admin routes has standard FastAPI 404 JSON body: `{"detail": "Not Found"}`

**Checkpoint**: Route isolation is verified. Admin endpoints are completely unreachable on the guest port.

---

## Phase 6: User Story 4 — Addon Administrator Configures Guest Port (Priority: P3)

**Goal**: The addon's `config.yaml` correctly declares the guest port (8099/tcp) with clear labeling, and the settings layer validates port configurations to prevent conflicts.

**Independent Test**: Inspect `addon/config.yaml` for correct ports section, ports_description, and schema. Run port conflict validation tests.

### Verification for User Story 4

- [ ] T014 [US4] Validate addon configuration and port conflict handling are correct
  - Verify `addon/config.yaml` has:
    - `"8099/tcp": 8099` in `ports:` section
    - `"8099/tcp": Guest captive portal (configure WiFi controller to redirect here)` in `ports_description:`
    - `guest_external_url: "url?"` in `schema:` section
  - Run `tests/unit/config/test_settings_guest.py` to confirm port conflict validation tests pass
  - Verify the s6 guest run script reads `guest_external_url` from addon options and exports `CP_GUEST_EXTERNAL_URL`
  - Verify no duplicate port configuration option exists in schema (FR-007 compliance)

**Checkpoint**: Guest port is configurable via HA's standard port mapping UI. No duplicate configuration surfaces.

---

## Phase 7: User Story 5 — Guest Portal Generates Correct Redirect URLs (Priority: P3)

**Goal**: Captive detection redirects on the guest listener use the configured external URL as the redirect base, so guest browsers navigate to the correct address. A warning is logged when the external URL is not configured.

**Independent Test**: Configure `guest_external_url`, trigger captive detection, and verify redirect Location headers use the external URL. Remove the configuration and verify a warning is logged.

### Tests for User Story 5

> **NOTE: Captive detection redirect tests (T009) should already cover external URL behavior. These tests focus on edge cases and the warning log.**

- [ ] T015 [P] [US5] Write integration tests for external URL redirect generation and fallback in tests/integration/test_guest_external_url.py
  - Add SPDX header
  - Test with `guest_external_url = "http://192.168.1.100:8099"`:
    - All seven captive detection endpoints redirect to `http://192.168.1.100:8099/guest/authorize`
  - Test with `guest_external_url = "https://portal.example.com"`:
    - Redirects use `https://portal.example.com/guest/authorize`
  - Test with `guest_external_url = ""` (empty/not configured):
    - Redirects use relative `/guest/authorize`
  - Test trailing slash stripping: if someone configures `http://192.168.1.100:8099/`, the validation in AppSettings should reject it (tested in T004) — but if it somehow gets through, redirects should not produce double slashes
  - Test that the same captive detection endpoints on the ingress app (via `create_app()`) still use `root_path` and are NOT affected by `guest_external_url`

### Implementation for User Story 5

- [ ] T016 [US5] Add startup warning log when guest_external_url is not configured in addon/src/captive_portal/guest_app.py
  - In `create_guest_app()`, after settings are loaded, check if `settings.guest_external_url` is empty
  - If empty, log a warning:
    ```python
    logger.warning(
        "guest_external_url is not configured. "
        "Captive portal detection redirects will use relative paths. "
        "Set guest_external_url in addon options for correct redirect URLs."
    )
    ```
  - This satisfies spec User Story 5, acceptance scenario 3 and edge case "external URL not configured"
  - Run `tests/integration/test_guest_external_url.py` to verify tests pass

**Checkpoint**: Redirect URLs are correct from the guest's network perspective. Missing configuration is clearly warned about.

---

## Phase 8: User Story 6 — System Health Monitoring Across Both Ports (Priority: P4)

**Goal**: Health, readiness, and liveness endpoints are available on the guest listener, returning the same response schemas as the ingress listener. Each listener reports its own health independently.

**Independent Test**: Send health check requests to the guest app's TestClient and verify correct responses.

### Tests for User Story 6

> **NOTE: Health router is already included in the guest app (T008). These tests verify it works correctly on the guest listener.**

- [ ] T017 [P] [US6] Write integration tests for health endpoints on guest listener in tests/integration/test_guest_listener_health.py
  - Add SPDX header
  - Create `TestClient(create_guest_app(settings=AppSettings(db_path=":memory:")))` fixture
  - Test `GET /api/health` → 200 OK with `{"status": "ok", "timestamp": "..."}`
  - Test `GET /api/ready` → 200 OK with `{"status": "ok", "timestamp": "...", "checks": {"database": "ok"}}`
  - Test `GET /api/live` → 200 OK with `{"status": "ok", "timestamp": "..."}`
  - Test health endpoint response schemas match the ingress listener's schemas exactly (use same Pydantic models: `HealthResponse`, `ReadinessResponse`, `LivenessResponse`)
  - Test readiness endpoint returns 503 when database is unavailable (if testable with in-memory DB teardown)

**Checkpoint**: Both listeners provide health endpoints. Monitoring systems can verify each listener independently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, linting, type checking, and documentation verification across all new and modified files.

- [ ] T018 [P] Run ruff linting across all new and modified files
  - `uv run ruff check addon/src/captive_portal/guest_app.py`
  - `uv run ruff check addon/src/captive_portal/config/settings.py`
  - `uv run ruff check addon/src/captive_portal/api/routes/captive_detect.py`
  - `uv run ruff check addon/src/captive_portal/web/middleware/security_headers.py`
  - `uv run ruff check tests/unit/test_guest_app_factory.py tests/unit/test_guest_app_routes.py tests/unit/config/test_settings_guest.py`
  - `uv run ruff check tests/integration/test_captive_detect_guest.py tests/integration/test_dual_port_isolation.py tests/integration/test_guest_external_url.py tests/integration/test_guest_listener_health.py`
  - Fix any issues found

- [ ] T019 [P] Run mypy type checking across all new and modified modules
  - `uv run mypy addon/src/captive_portal/guest_app.py`
  - `uv run mypy addon/src/captive_portal/config/settings.py`
  - `uv run mypy addon/src/captive_portal/api/routes/captive_detect.py`
  - `uv run mypy addon/src/captive_portal/web/middleware/security_headers.py`
  - Fix any type errors — all new code must have complete type annotations

- [ ] T020 [P] Verify SPDX license headers on all new files
  - Every new file must have:
    - Python files: `# SPDX-FileCopyrightText: 2026 Andrew Grimberg` and `# SPDX-License-Identifier: Apache-2.0`
    - Bash scripts: `# SPDX-FileCopyrightText: 2026 Andrew Grimberg` and `# SPDX-License-Identifier: Apache-2.0`
  - New files checklist:
    - `addon/src/captive_portal/guest_app.py`
    - `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/run`
    - `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/finish`
    - `tests/unit/test_guest_app_factory.py`
    - `tests/unit/test_guest_app_routes.py`
    - `tests/unit/config/test_settings_guest.py`
    - `tests/integration/test_captive_detect_guest.py`
    - `tests/integration/test_dual_port_isolation.py`
    - `tests/integration/test_guest_external_url.py`
    - `tests/integration/test_guest_listener_health.py`

- [ ] T021 Run quickstart.md validation and full test suite end-to-end
  - Run `uv run pytest` — ALL tests (existing + new) must pass
  - Run `uv run pre-commit run --all-files` — all hooks must pass
  - Verify the quickstart.md code examples are accurate post-implementation:
    - `from captive_portal.guest_app import create_guest_app` works
    - `create_guest_app(settings=AppSettings(db_path=":memory:"))` returns a working app
    - TestClient examples from quickstart.md produce expected results

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately. All 3 tasks are parallel.
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) completion — BLOCKS all user stories.
  - T004 and T005 can run in parallel (different files, no inter-dependency)
  - T006 depends on T004 (TDD: test first, implement second)
  - T007 depends on T005 and T006 (needs parameterized middleware + settings to write meaningful guest app tests)
  - T008 depends on T007 (TDD: test first, implement second)
- **User Stories (Phase 3+)**: All depend on Foundational (Phase 2) completion.
  - User stories can proceed in priority order (P1 → P2 → P3 → P4)
  - US3 (Phase 5) can start in parallel with US1 (Phase 3) since it tests existing guest app behavior
  - US2 (Phase 4) should run after US1 to confirm no regressions from captive_detect.py changes
  - US4, US5, US6 can proceed in any order after US1
- **Polish (Phase 9)**: Depends on all user story phases being complete.

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational (Phase 2). This is the MVP.
- **US2 (P2)**: Depends on US1 completion (to verify captive_detect.py changes don't break ingress).
- **US3 (P2)**: Can start after Foundational. Tests route isolation built into guest_app.py.
- **US4 (P3)**: Can start after Foundational. Validates configuration from Setup phase.
- **US5 (P3)**: Depends on US1 (builds on captive detection redirect changes from T010).
- **US6 (P4)**: Can start after Foundational. Tests health router on guest app.

### Within Each Phase

- Tests (where included) MUST be written FIRST and MUST FAIL before implementation
- Implementation makes tests GREEN
- Run linting/type checks after each implementation task
- Commit after each task with SPDX headers, DCO sign-off, Conventional Commits

### Parallel Opportunities

- **Phase 1**: All 3 setup tasks (T001, T002, T003) can run in parallel
- **Phase 2**: T004 and T005 can run in parallel; then T006; then T007; then T008
- **Phase 3 + Phase 5**: US1 tests (T009) and US3 tests (T012, T013) can run in parallel
- **Phase 6 + Phase 7 + Phase 8**: US4 (T014), US5 (T015), and US6 (T017) can run in parallel
- **Phase 9**: T018, T019, T020 can run in parallel; T021 runs last

---

## Parallel Example: Foundational Phase

```text
# Wave 1 — parallel (different files, no dependencies):
Task T004: "Write unit tests for guest settings in tests/unit/config/test_settings_guest.py"
Task T005: "Parameterize SecurityHeadersMiddleware in addon/src/captive_portal/web/middleware/security_headers.py"

# Wave 2 — sequential (depends on T004):
Task T006: "Add guest_external_url to AppSettings in addon/src/captive_portal/config/settings.py"

# Wave 3 — sequential (depends on T005, T006):
Task T007: "Write unit tests for guest app factory in tests/unit/test_guest_app_factory.py"

# Wave 4 — sequential (depends on T007):
Task T008: "Create guest app factory in addon/src/captive_portal/guest_app.py"
```

## Parallel Example: User Stories

```text
# After Foundational completes, these can run in parallel:

# Stream A — US1 (P1, MVP):
Task T009: "Write captive detection integration tests"
Task T010: "Update captive_detect.py for guest_external_url"

# Stream B — US3 (P2, route isolation):
Task T012: "Write admin route 404 unit tests"
Task T013: "Write dual-port isolation integration tests"

# After US1 completes:
Task T011: "Run full test suite for backward compatibility (US2)"
Task T015: "Write external URL redirect integration tests (US5)"
Task T016: "Add startup warning log for missing external URL (US5)"
Task T017: "Write guest listener health integration tests (US6)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (s6 files, config, Dockerfile)
2. Complete Phase 2: Foundational (settings, middleware, guest app factory)
3. Complete Phase 3: User Story 1 (captive detection on guest listener)
4. **STOP and VALIDATE**: Run all tests, verify guest captive detection flow works
5. Deploy/demo if ready — guests can reach the captive portal

### Incremental Delivery

1. Setup + Foundational → Guest app factory exists and starts
2. Add US1 → Captive detection works on guest listener → **MVP deployed!**
3. Add US2 → Backward compatibility confirmed → No regressions
4. Add US3 → Route isolation verified → Security guaranteed
5. Add US4 → Configuration validated → Admin can configure port
6. Add US5 → Redirect URLs correct → Full captive flow works end-to-end
7. Add US6 → Health monitoring → Production-ready observability
8. Polish → Linting, type checks, SPDX headers, full validation

### Each Story Adds Value Without Breaking Previous Stories

- US1: Guests can reach the portal (core value)
- US2: Admins confirmed unaffected (safety)
- US3: Security isolation proven (trust)
- US4: Configuration is clean (operability)
- US5: Redirects are correct (reliability)
- US6: Health is observable (production readiness)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD is NON-NEGOTIABLE: write tests first, verify they fail, then implement
- All new files require SPDX headers: `SPDX-FileCopyrightText: 2026 Andrew Grimberg` / `SPDX-License-Identifier: Apache-2.0`
- Commit after each task or logical group with DCO sign-off and Conventional Commits
- Stop at any checkpoint to validate independently
- The ingress app (`create_app()`) is NEVER modified — only `captive_detect.py`, `settings.py`, and `security_headers.py` are updated
- Reference the `rentalsync-bridge` repository for s6-overlay multi-service patterns
