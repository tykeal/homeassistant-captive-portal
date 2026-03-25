SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Addon Structure Refactor

**Input**: Design documents from `/specs/003-addon-structure-refactor/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not requested — no test tasks included. The existing test suite (441+ tests) serves as the authoritative validation of application correctness (SC-002). Existing integration tests (`test_addon_build_run.py`, `test_addon_startup_wiring.py`) cover build and startup scenarios.

**Organization**: Tasks are grouped by user story. User Stories 3, 4, and 5 require no additional implementation beyond earlier phases; their satisfaction is documented in the Dependencies section.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US6)
- Include exact file paths in descriptions

## Path Conventions

- **Addon build context**: `addon/` (Docker build context for HA Supervisor)
- **Application source**: `addon/src/captive_portal/`
- **s6-overlay services**: `addon/rootfs/etc/s6-overlay/s6-rc.d/`
- **Repository root**: Development workspace (tests, linting, type-checking)
- **Reference implementation**: A private Home Assistant addon (`rentalsync-bridge`) used during design (not part of this repo; contact the maintainer for details).

---

## Phase 1: Setup

**Purpose**: No separate setup phase needed — this is a structural refactor of an existing project. The repository, branch, and all source code are already in place.

---

## Phase 2: Foundational (Build Backend & Lock File)

**Purpose**: Core build tooling changes that MUST be complete before any user story implementation

**Plan cross-reference**: Corresponds to plan.md Phase 1 items 1–2 (pyproject.toml + uv.lock)

**⚠️ CRITICAL**: The Dockerfile rewrite (Phase 3) depends on both the hatchling build backend and the frozen lock file being in place. No user story work can begin until this phase is complete.

- [ ] T001 Switch addon/pyproject.toml from setuptools to hatchling build backend in addon/pyproject.toml
- [ ] T002 Generate frozen dependency lock file by running `cd addon && uv lock` to create addon/uv.lock

**T001 Details**:

- Replace `[build-system]` requires from `["setuptools", "wheel"]` to `["hatchling"]`
- Replace `build-backend` from `"setuptools.build_meta"` to `"hatchling.build"`
- Remove the entire `[tool.setuptools.packages.find]` section (`where = ["src"]`)
- Remove the entire `[tool.setuptools.package-data]` section (`captive_portal = [...]`)
- Add new section `[tool.hatch.build.targets.wheel]` with:
  - `packages = ["src/captive_portal"]`
  - Explicit inclusion of runtime assets so templates and themes are packaged:

    ```toml
    [tool.hatch.build.targets.wheel]
    packages = ["src/captive_portal"]
    include = [
      "src/captive_portal/web/templates/**",
      "src/captive_portal/web/themes/**",
    ]
    ```
- Keep the existing `[project]` section unchanged (name, version, dependencies, etc.)
- Keep the existing SPDX header (2025) unchanged
- Reference pattern: rentalsync-bridge `pyproject.toml` uses identical hatchling setup

**T002 Details**:

- Run `cd addon && uv lock` to generate `addon/uv.lock` from `addon/pyproject.toml`
- This lock file pins all runtime dependencies for reproducible Docker builds (`uv sync --frozen`)
- The file is auto-generated; SPDX compliance is handled via existing REUSE.toml annotation (`"addon/uv.lock"` is already listed)
- Verify the lock resolves all dependencies listed in `addon/pyproject.toml` (fastapi, uvicorn, httpx, sqlmodel, pydantic, jinja2, passlib, argon2-cffi, email-validator, python-multipart)
- This file MUST be a regular file (not a symlink) — symlinks don't resolve inside the Docker build context

**Checkpoint**: `addon/pyproject.toml` uses hatchling and `addon/uv.lock` exists with all runtime dependencies resolved

---

## Phase 3: User Story 1 — HA Supervisor Builds and Starts the Addon (Priority: P1) 🎯 MVP

**Goal**: Make the addon buildable by HA Supervisor using only the `addon/` directory as build context, and functional after startup (serving the captive portal web interface on port 8080)

**Plan cross-reference**: Corresponds to plan.md Phase 1 items 3–5 (build.yaml, Dockerfile, run script) and Phase 2 items 1–2 (config.yaml, config.json deletion)

**Independent Test**: Add the repository URL to a Home Assistant instance, install the addon, verify it builds without errors, starts, and serves the web interface on the configured port

### Implementation for User Story 1

- [ ] T003 [P] [US1] Update addon/build.yaml to use Python-specific HA base images in addon/build.yaml
- [ ] T004 [P] [US1] Rewrite addon/Dockerfile with two-phase uv sync --frozen install pattern in addon/Dockerfile
- [ ] T005 [P] [US1] Create addon/config.yaml by converting addon/config.json to YAML format as addon/config.yaml
- [ ] T006 [US1] Delete addon/config.json after YAML replacement is in place
- [ ] T007 [P] [US1] Update s6-overlay run script for new .venv path in addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run

**T003 Details**:

- Change `amd64` from `ghcr.io/home-assistant/amd64-base:3.21` to `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21`
- Change `aarch64` from `ghcr.io/home-assistant/aarch64-base:3.21` to `ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21`
- Python-specific base images pre-install Python 3.13 and the standard library, eliminating the `apk add python3` step in the Dockerfile
- Keep existing SPDX header (2025) and YAML structure unchanged
- Reference: research.md §2 "Base Container Image"

**T004 Details** (reference: rentalsync-bridge Dockerfile):

- Update default `BUILD_FROM` arg from `ghcr.io/home-assistant/amd64-base:latest` to `ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21`
- Keep `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv`
- Remove `RUN apk add --no-cache python3` (Python base image provides it)
- **Build dependencies note**: Unlike the reference (which needs `gcc musl-dev libffi-dev` for `cryptography`), captive-portal's runtime deps (`argon2-cffi`, `passlib[bcrypt]`, `uvicorn[standard]`) provide pre-built musllinux wheels for amd64/aarch64. No `apk add` of compiler toolchain is needed. If a future dependency requires native compilation on Alpine, add `gcc musl-dev` here.
- Remove `ENV VIRTUAL_ENV=/opt/venv` and `RUN uv venv "$VIRTUAL_ENV"` and the old `ENV PATH="$VIRTUAL_ENV/bin:$PATH"` (uv sync creates `.venv` automatically in the project directory)
- Change dependency install to two-phase pattern for Docker layer caching:
  1. `COPY pyproject.toml uv.lock ./` then `RUN uv sync --frozen --no-dev --no-install-project` (dependencies only — cached when only source changes)
  2. `COPY src/ ./src/` and `COPY README.md ./` then `RUN uv sync --frozen --no-dev` (installs the project with source)
- Replace old PATH with `ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1`
- Keep `COPY rootfs /` and `EXPOSE 8080`
- Add `RUN chmod +x /etc/s6-overlay/s6-rc.d/captive-portal/run` after copying rootfs
- Remove any CMD/ENTRYPOINT — s6-overlay from the base image handles process startup
- Keep existing SPDX header (2025) unchanged
- Reference: research.md §3 "Dockerfile Pattern"

**T005 Details**:

- Create `addon/config.yaml` with SPDX header lines:
  ```
  # SPDX-FileCopyrightText: 2026 Andrew Grimberg
  # SPDX-License-Identifier: Apache-2.0
  ```
- Convert all fields from `addon/config.json` preserving exact semantics:
  - `name: "Captive Portal Guest Access"`
  - `version: "0.0.0-dev"`
  - `slug: "captive_portal_guest_access"`
  - `description: "Guest network captive portal integrating TP-Omada and Home Assistant"`
  - `url: "https://example.com/placeholder"`
  - `arch:` as YAML list `[amd64, aarch64]`
  - `startup: services`, `init: false`, `panel_admin: true`, `homeassistant_api: true`, `ingress: false`
  - `webui: "http://[HOST]:[PORT:8080]"`
  - `ports:` with quoted key `"8080/tcp": 8080`
  - `ports_description:` with quoted key `"8080/tcp": "Web admin & portal"`
  - `schema:` with nested option definitions (log_level, session_idle_timeout, session_max_duration)
- Reference: contracts/ha-supervisor-contract.md §1, data-model.md §2.1

**T006 Details**:

- Delete `addon/config.json` — it is fully replaced by `addon/config.yaml` from T005
- HA Supervisor reads `config.yaml` (preferred) or `config.json`; with YAML present, JSON is unnecessary
- Reference: research.md §4 "Addon Config Format"

**T007 Details**:

- Replace `exec "${VIRTUAL_ENV}/bin/python" -m uvicorn \` with `exec python -m uvicorn \` (`python` is on PATH via `/app/.venv/bin`)
- Keep all uvicorn arguments unchanged: `captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080`
- Keep the `bashio::config 'log_level'` reading and `bashio::log.info` startup message
- Keep the shebang (`#!/command/with-contenv bashio`), shellcheck directive, and all comments
- Keep existing SPDX header (2025) unchanged
- The `finish` script and `type` file require no changes — they are already correct
- Reference: research.md §8 "s6-overlay Service Configuration Assessment"

**Checkpoint**: `docker build addon/` succeeds; container starts via s6-overlay and responds on port 8080; HA Supervisor can build and start the addon

---

## Phase 4: User Story 2 — Developer Runs Tests from the Repo Root (Priority: P2)

**Goal**: Preserve the development workflow so that a developer can clone the repo, install dependencies, and run the full test suite unchanged from the repo root

**Plan cross-reference**: Corresponds to plan.md Phase 2 items 3 (root src/ removal) and 5 (workspace verification)

**Independent Test**: Clone the repository, run `uv sync && uv run pytest` from the root, verify all 441+ tests pass with zero failures

### Implementation for User Story 2

- [ ] T008 [US2] Remove stale root src/ directory that contains only empty directories and \_\_pycache\_\_ artifacts
- [ ] T009 [US2] Regenerate root uv.lock and verify full development workflow from repo root

**T008 Details**:

- Delete the entire `src/` directory at the repository root via `rm -rf src/` (this directory contains NO git-tracked files — only untracked empty subdirectories and stale `__pycache__` bytecode artifacts, so `git rm` will not work)
- The canonical source code lives at `addon/src/captive_portal/`
- Root `pyproject.toml` workspace config (`members = ["addon"]`) does not reference root `src/`
- Root `.mypy.ini` already uses `mypy_path = addon/src` — no update needed
- Reference: research.md §6 "Stale Root src/ Directory Cleanup"

**T009 Details**:

- Run `uv lock` from repo root to regenerate `uv.lock` (reflects addon `pyproject.toml` hatchling changes)
- Run `uv sync` to update the editable install with the new hatchling build backend
- Verify development workflow:
  - `uv run pytest` — all 441+ tests must pass with zero failures and zero test modifications
  - `uv run ruff check addon/src/ tests/` — must pass
  - `uv run ruff format --check addon/src/ tests/` — must pass
  - `uv run mypy addon/src/captive_portal/` — must pass (uses `.mypy.ini` with `mypy_path = addon/src`)
  - `uv run interrogate addon/src/captive_portal/` — must pass
- If any tool fails due to the hatchling switch or `src/` removal, fix the root configuration (likely `pyproject.toml` or `.mypy.ini`)
- Reference: research.md §9 "Development Workflow Impact Assessment"

**Checkpoint**: Full test suite passes from repo root; all linting, formatting, and type-checking tools pass

---

## Phase 5: User Story 3 — Developer Builds the Addon Image Locally (Priority: P3)

**Goal**: Developers can build and run the addon container locally via `docker build addon/` without a full HA instance

**Independent Test**: Run `docker build -t captive-portal:dev addon/` and then `docker run --rm -p 8080:8080 captive-portal:dev`, verify the health endpoint responds

> **No additional implementation tasks required.** This story is fully satisfied by:
>
> - **T004** — Dockerfile includes a working default `BUILD_FROM` arg (`ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21`) enabling local `docker build addon/` without passing build args
> - **T001 + T002** — hatchling build backend and frozen lock file enable `uv sync --frozen` in the Dockerfile
> - **T007** — updated run script ensures the application process starts correctly under s6-overlay
>
> The existing integration test `tests/integration/test_addon_build_run.py` validates this scenario.

---

## Phase 6: User Story 4 — Addon Restarts After a Crash (Priority: P4)

**Goal**: The s6-overlay process supervisor automatically restarts the application process if it exits unexpectedly

**Independent Test**: Kill the application process inside the running container (`kill -9 <pid>`) and verify s6-overlay restarts it automatically within 30 seconds

> **No additional implementation tasks required.** This story is fully satisfied by:
>
> - **T007** — updated run script with correct `.venv` path ensures the service starts correctly under s6-overlay supervision
> - Existing `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/type` contains `longrun` — s6-overlay automatically restarts long-running services on unexpected exit
> - Existing `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/finish` logs exit codes for debugging — this is an enhancement over the reference implementation
> - Existing `addon/rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/captive-portal` registers the service with s6
>
> All s6-overlay service definitions are already correct and require no modification beyond the run script venv path update (T007).

---

## Phase 7: User Story 5 — Addon Builds on Multiple Architectures (Priority: P5)

**Goal**: The addon builds and runs correctly on both amd64 and aarch64 architectures

**Independent Test**: Verify `build.yaml` maps both architectures to correct Python-specific base images, `config.yaml` declares both architectures, and the Dockerfile uses `ARG BUILD_FROM`/`FROM ${BUILD_FROM}` for Supervisor-driven image selection

> **No additional implementation tasks required.** This story is fully satisfied by:
>
> - **T003** — `build.yaml` maps both `amd64` and `aarch64` to their respective Python-specific base images (`ghcr.io/home-assistant/{arch}-base-python:3.13-alpine3.21`)
> - **T005** — `config.yaml` declares `arch: [amd64, aarch64]`, matching the `build.yaml` entries exactly
> - **T004** — Dockerfile uses `ARG BUILD_FROM` / `FROM ${BUILD_FROM}` pattern, allowing the HA Supervisor to inject the architecture-specific base image at build time
>
> Every architecture listed in `config.yaml:arch` has a corresponding entry in `build.yaml:build_from` (per contracts/ha-supervisor-contract.md §2).

---

## Phase 8: User Story 6 — All New and Modified Files Have License Headers (Priority: P6)

**Goal**: Maintain REUSE/SPDX compliance — every new file has correct license headers and REUSE.toml accurately reflects the file layout

**Plan cross-reference**: Corresponds to plan.md Phase 2 item 4 (REUSE.toml update)

**Independent Test**: Run a REUSE compliance check (`reuse lint` or manual inspection) and verify no missing headers

### Implementation for User Story 6

- [ ] T010 [P] [US6] Update REUSE.toml for new and changed file patterns in REUSE.toml
- [ ] T011 [US6] Verify SPDX headers on all new and modified files across the repository

**T010 Details**:

- Review existing REUSE.toml annotations against the final file state after Phases 2–4:
  - `addon/uv.lock` — already covered by existing annotation (verify it still matches after regeneration in T002)
  - `addon/config.yaml` — new file with inline SPDX comments; verify it is covered by an existing glob or add a new annotation pattern
  - The existing `**.json` glob covered `config.json`; with `config.json` deleted, the glob is harmless but no longer matches addon config
  - `addon/rootfs/.../type` and `user/contents.d/captive-portal` — already covered by existing annotations (verify unchanged)
- Remove annotations for deleted file patterns if they are explicitly listed (check if `config.json` has a specific entry vs. the broad `**.json` glob)
- Ensure no annotation references files that no longer exist (e.g., root `src/` paths)
- Keep the existing SPDX header (2025) on REUSE.toml itself

**T011 Details**:

- **New files** requiring `2026` SPDX headers (as specified by user):
  - `addon/config.yaml` — inline YAML comments: `# SPDX-FileCopyrightText: 2026 Andrew Grimberg` / `# SPDX-License-Identifier: Apache-2.0`
  - `specs/003-addon-structure-refactor/tasks.md` — plain text header at top of file
- **Modified files** retaining existing `2025` SPDX headers (verify unchanged):
  - `addon/Dockerfile`, `addon/build.yaml`, `addon/pyproject.toml`, `addon/rootfs/.../captive-portal/run`
- **Generated files** covered by REUSE.toml (no inline header):
  - `addon/uv.lock`, `uv.lock` (root)
- Run `reuse lint` if the tool is available, or manually inspect all files touched in this feature branch
- Cross-reference against data-model.md §3 "File Lifecycle" to ensure every CREATE/MODIFY/DELETE action preserved compliance

**Checkpoint**: All new files have correct SPDX headers; REUSE.toml accurately reflects current file patterns; no compliance gaps

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation across all user stories

- [ ] T012 Run quickstart.md developer workflow validation end-to-end per specs/003-addon-structure-refactor/quickstart.md

**T012 Details**:

- Follow `specs/003-addon-structure-refactor/quickstart.md` step by step:
  1. **Clone and Install**: `uv sync` from repo root — must succeed
  2. **Run Tests**: `uv run pytest` — all 441+ tests pass
  3. **Run Linting**: `uv run ruff check addon/src/ tests/` and `uv run ruff format --check addon/src/ tests/` — pass
  4. **Type Checking**: `uv run mypy addon/src/captive_portal/` — pass
  5. **Docstring Coverage**: `uv run interrogate addon/src/captive_portal/` — pass
  6. **Build Container**: `docker build -t captive-portal:dev addon/` — succeeds
  7. **Run Container**: `docker run --rm -p 8080:8080 captive-portal:dev` — starts, health endpoint responds
- Document any deviations or issues found and fix before marking complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Skipped — no tasks needed
- **Phase 2 (Foundational)**: No external dependencies — can start immediately
  - T001 → T002 (lock file generation needs correct pyproject.toml first)
- **Phase 3 (US1)**: Depends on Phase 2 completion (Dockerfile needs hatchling + lock file)
  - T003, T004, T005, T007 can all run in parallel [P] (4 independent files)
  - T006 depends on T005 (delete config.json only after config.yaml exists)
- **Phase 4 (US2)**: Depends on Phase 2 completion (hatchling switch affects workspace editable install)
  - T008 → T009 (verify dev workflow after stale directory removal)
  - **Can run in parallel with Phase 3** (different files, no conflicts)
- **Phase 5 (US3)**: No additional tasks — satisfied by Phase 2 + Phase 3
- **Phase 6 (US4)**: No additional tasks — satisfied by Phase 3 (T007)
- **Phase 7 (US5)**: No additional tasks — satisfied by Phase 3 (T003, T005)
- **Phase 8 (US6)**: Depends on all file changes being complete (Phases 2–4)
- **Phase 9 (Polish)**: Depends on all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (Phase 2) — no dependencies on other stories
- **US2 (P2)**: Depends on Foundational (Phase 2) — can run in parallel with US1
- **US3 (P3)**: Satisfied by US1 completion — no additional tasks or dependencies
- **US4 (P4)**: Satisfied by US1 (T007 run script update) — no additional tasks
- **US5 (P5)**: Satisfied by US1 (T003 build.yaml + T005 config.yaml) — no additional tasks
- **US6 (P6)**: Depends on all file changes from US1 + US2 being complete

### Within User Story 1 (Phase 3)

- T003 (build.yaml), T004 (Dockerfile), T005 (config.yaml), T007 (run script) — all different files, can run in parallel
- T006 (delete config.json) must follow T005 (config.yaml must exist first)

### Parallel Opportunities

- **Phase 3 parallel group**: T003 + T004 + T005 + T007 (4 independent files, max parallelism)
- **Phase 3 + Phase 4 cross-phase**: US1 and US2 can proceed simultaneously after Phase 2 completes
- **Phase 8**: T010 (REUSE.toml) is independent within its phase

---

## Parallel Example: User Story 1

```bash
# After Phase 2 completes, launch all independent US1 tasks together (4 different files):
Task: "Update addon/build.yaml to Python-specific HA base images"           # T003
Task: "Rewrite addon/Dockerfile with uv sync --frozen pattern"              # T004
Task: "Create addon/config.yaml from addon/config.json"                     # T005
Task: "Update s6 run script for new .venv path"                             # T007

# Then sequentially (depends on T005):
Task: "Delete addon/config.json"                                            # T006
```

## Parallel Example: Cross-Phase

```bash
# Phase 3 and Phase 4 can run in parallel after Phase 2:
# Stream A (US1): T003 + T004 + T005 + T007 → T006
# Stream B (US2): T008 → T009
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001–T002) — hatchling build backend + frozen lock file
2. Complete Phase 3: User Story 1 (T003–T007) — build config, Dockerfile, addon config, s6 run script
3. **STOP and VALIDATE**: `docker build addon/` succeeds; container starts and responds on port 8080
4. This also satisfies US3 (local builds), US4 (crash restart), and US5 (multi-arch)
5. MVP delivers 5 of 6 user stories with 7 tasks

### Incremental Delivery

1. Phase 2 → Foundational ready (hatchling + lock file)
2. Phase 3 → US1 complete → addon builds and runs under HA Supervisor (**MVP!**)
3. Phase 4 → US2 complete → developer workflow preserved, all 441+ tests pass
4. Phase 8 → US6 complete → REUSE/SPDX license compliance verified
5. Phase 9 → Polish → end-to-end quickstart.md validation

### Parallel Team Strategy

With two developers:

1. Both complete Phase 2 together (2 sequential tasks)
2. Once Foundational is done:
   - Developer A: User Story 1 (Phase 3) — addon build and config files
   - Developer B: User Story 2 (Phase 4) — stale cleanup and dev workflow verification
3. Both converge on US6 (Phase 8) and Polish (Phase 9)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase
- [Story] label maps tasks to specific user stories for traceability
- US3, US4, US5 have no unique implementation tasks — they describe verification scenarios satisfied by US1 changes
- No test tasks included — the existing 441+ test suite validates application correctness (SC-002)
- Commit after each task or logical group with proper DCO sign-off (per constitution principle V)
- All new files use SPDX header: `SPDX-FileCopyrightText: 2026 Andrew Grimberg` / `SPDX-License-Identifier: Apache-2.0`
- Modified files retain their existing 2025 SPDX headers unchanged
- Reference implementation (`rentalsync-bridge`, private repo; contact maintainer) for Dockerfile, build.yaml, config.yaml, pyproject.toml patterns
