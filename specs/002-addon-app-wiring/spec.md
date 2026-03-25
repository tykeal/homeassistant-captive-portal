SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Wire Real Application into Addon Container

**Feature Branch**: `002-addon-app-wiring`
**Created**: 2025-07-14
**Status**: Draft
**Input**: User description: "Wire real captive_portal application into Home Assistant addon container"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Addon Starts the Real Application (Priority: P1)

As a Home Assistant administrator, I install the Captive Portal addon and start it. The addon launches the full captive portal application — not the current placeholder — so that all existing routes, database models, middleware, authentication, and the admin UI are available on port 8080.

**Why this priority**: Without the real application running inside the addon container, no other addon functionality is accessible. This is the foundational integration that makes the addon useful instead of a stub.

**Independent Test**: Can be fully tested by installing the addon in a Home Assistant environment, starting it, and confirming the readiness endpoint (`/api/ready`) reports the application as ready, the admin login page loads, and the guest portal page loads — delivering a working captive portal system.

**Acceptance Scenarios**:

1. **Given** the addon is installed and started, **When** a user navigates to the addon's web UI on port 8080, **Then** the full captive portal application responds (not the placeholder).
2. **Given** the addon is started, **When** the readiness endpoint (`/api/ready`) is requested, **Then** it returns a success status confirming the application and its database dependencies are operational.
3. **Given** the addon is started for the first time, **When** the application initializes, **Then** all database tables are created automatically and the application is ready to serve requests within 30 seconds of container start.
4. **Given** the addon is restarted, **When** it starts again, **Then** all previously stored data (admin accounts, access grants, vouchers, audit logs) is preserved and accessible.

---

### User Story 2 - Administrator Configures the Addon from Home Assistant UI (Priority: P2)

As a Home Assistant administrator, I configure the captive portal addon through the standard Home Assistant addon configuration panel. I can set the log verbosity, session timeout durations, and other operational parameters without needing to edit files or SSH into the container.

**Why this priority**: Configurability through the HA UI is the standard expectation for all Home Assistant addons. Without this, administrators would have no way to tune the addon's behavior, making it rigid and hard to adapt to different deployment environments.

**Independent Test**: Can be tested by opening the addon's configuration tab in the HA UI, changing settings (e.g., log level, session timeout), restarting the addon, and confirming the new settings take effect in the application's behavior.

**Acceptance Scenarios**:

1. **Given** the addon is installed, **When** an administrator opens the addon's configuration tab, **Then** they see configurable options for log level, session idle timeout, and session maximum duration with sensible defaults pre-filled.
2. **Given** an administrator changes the log level to "debug" in the configuration panel, **When** the addon is restarted, **Then** the application produces debug-level log output.
3. **Given** an administrator sets the session idle timeout to 15 minutes, **When** the addon restarts, **Then** admin sessions expire after 15 minutes of inactivity.
4. **Given** no configuration changes are made, **When** the addon is started with default settings, **Then** the application runs with reasonable defaults (info-level logging, 30-minute idle timeout, 8-hour maximum session).

---

### User Story 3 - Guest Portal Pages Render Correctly (Priority: P2)

As a guest attempting to connect to the WiFi network, I am redirected to the captive portal page. The portal loads with properly styled HTML pages — including the authorization form, welcome page, and error page — so I can complete the WiFi authorization process.

**Why this priority**: The guest-facing portal is the primary user interface of the entire system. If templates or static assets are missing from the container image, guests see broken or blank pages and cannot authorize their devices.

**Independent Test**: Can be tested by navigating to the guest portal URL in a browser and confirming that all HTML pages render with proper styling, forms are interactive, and no 404 errors occur for templates or static resources.

**Acceptance Scenarios**:

1. **Given** the addon is running, **When** a guest navigates to the portal authorization page, **Then** a styled HTML page loads with the booking code entry form.
2. **Given** the addon is running, **When** any guest-facing page is requested, **Then** all associated stylesheets and static assets load successfully (no 404 errors for CSS, images, or other resources).
3. **Given** the addon is running, **When** the admin navigates to the admin dashboard, **Then** the admin HTML templates render correctly with proper styling.

---

### User Story 4 - Application Graceful Shutdown (Priority: P3)

As a Home Assistant administrator, when I stop or restart the addon, the application shuts down cleanly — closing database connections and finishing in-progress requests — so that no data corruption occurs.

**Why this priority**: Graceful shutdown prevents database corruption and data loss. While less visible than startup, it is essential for reliability in a system that manages persistent access grants and audit records.

**Independent Test**: Can be tested by stopping the addon while requests are being processed and verifying the database remains consistent and uncorrupted upon restart.

**Acceptance Scenarios**:

1. **Given** the addon is running, **When** the addon is stopped via the HA UI, **Then** the application closes database connections cleanly before the container exits.
2. **Given** the addon is running with active database operations, **When** the addon is restarted, **Then** the database is not corrupted and all previously committed data is intact.

---

### User Story 5 - Multi-Architecture Support (Priority: P3)

As a Home Assistant administrator running on different hardware (Intel/AMD PC, Raspberry Pi, etc.), the addon container builds and runs correctly on both amd64 and aarch64 architectures.

**Why this priority**: Home Assistant runs on diverse hardware. Multi-architecture support ensures the addon is available to the full Home Assistant user base, not just those on x86 machines.

**Independent Test**: Can be tested by building the Docker image for both amd64 and aarch64 targets and confirming each image starts successfully and serves the application.

**Acceptance Scenarios**:

1. **Given** the addon is built for amd64 architecture, **When** it is installed and started on an amd64 Home Assistant system, **Then** the application starts and functions correctly.
2. **Given** the addon is built for aarch64 architecture, **When** it is installed and started on an aarch64 Home Assistant system (e.g., Raspberry Pi 4/5), **Then** the application starts and functions correctly.

---

### Edge Cases

- What happens when the database file does not exist on first startup? The application must create the database and all tables automatically.
- What happens when the /data/ directory is not writable? The application must fail with a clear error message rather than crashing silently.
- What happens when the addon configuration JSON contains invalid values (e.g., negative timeout, unknown log level)? For each invalid option, the application must ignore that specific addon configuration value, then apply the normal precedence rules (environment variable for that option, if set and valid, otherwise the built-in default), and log a warning describing the invalid value and the effective value used.
- What happens when the addon is started but the Python package has a missing dependency? The container must fail fast with a clear error in the addon log, not hang indefinitely.
- What happens when the database schema has changed between addon versions? The application must handle schema migration or at minimum not crash on startup (existing tables should remain usable).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The addon container MUST include the complete captive portal application with all its routers, models, middleware, security components, services, and integrations.
- **FR-002**: The addon container MUST install all application dependencies (as defined in the project's package metadata) into an isolated environment so they do not conflict with system packages.
- **FR-003**: The addon MUST start the full captive portal application on port 8080 when the container starts, replacing the current placeholder startup behavior.
- **FR-004**: The application MUST automatically initialize the database (create all required tables) on first startup before serving any requests.
- **FR-005**: The database MUST be stored in a persistent location that survives addon restarts and upgrades.
- **FR-006**: The addon MUST expose a configuration schema in its manifest so that Home Assistant displays configurable options in the addon's configuration panel.
- **FR-007**: The configuration schema MUST include options for: log level (with a default of "info"), session idle timeout in minutes (default 30), and session maximum duration in hours (default 8).
- **FR-008**: The application MUST read configuration values from the addon's options mechanism (the file written by the Home Assistant Supervisor) and apply them at startup.
- **FR-009**: The application MUST provide a settings/configuration layer that merges addon options, environment variables, and sensible defaults — with addon options taking precedence over environment variables, and environment variables taking precedence over defaults. If a specific addon option value is invalid (for example, the wrong type or outside the allowed range), the application MUST treat that option as unset for precedence purposes: it MUST ignore only that invalid value, then attempt to resolve the setting from the corresponding environment variable, and finally fall back to the built-in default if no valid value is found.
- **FR-010**: All guest portal HTML templates MUST be included in the container image and served correctly by the application.
- **FR-011**: All static assets (stylesheets, images, scripts) MUST be included in the container image and accessible via their expected URL paths.
- **FR-012**: The application MUST perform a clean shutdown when the container receives a stop signal — closing database connections and releasing resources.
- **FR-013**: The addon MUST build and run on both amd64 and aarch64 architectures using the existing multi-architecture build mechanism.
- **FR-014**: All existing routes and their URL paths MUST remain unchanged — the addon wiring MUST NOT alter the application's API contract.
- **FR-015**: The existing test suite MUST continue to pass without modification — the addon wiring MUST NOT break any existing application logic or test expectations.
- **FR-016**: The application startup process MUST log the effective configuration values (excluding secrets) so administrators can verify settings from the addon log.

### Key Entities

- **Addon Configuration**: The set of user-facing settings exposed through the Home Assistant addon configuration panel. Includes operational parameters like log level and session timeouts. Written by the HA Supervisor and read by the application at startup.
- **Application Settings**: The internal configuration object that consolidates addon options, environment variables, and defaults into a single source of truth used by the application throughout its lifecycle.
- **Database**: The persistent SQLite store holding all application data (admin accounts, access grants, vouchers, audit logs, portal configuration). Located in the addon's persistent data directory and initialized automatically on first run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The addon starts and serves the full application within 30 seconds of container start on standard hardware.
- **SC-002**: All application routes respond correctly when the addon is running — verified by requesting each route group's primary endpoint and receiving a valid response (not a 404 or 500 error).
- **SC-003**: Guest portal pages load completely with all templates and static assets — zero 404 errors for any resource referenced by the HTML pages.
- **SC-004**: Configuration changes made through the Home Assistant UI take effect after addon restart — verified by changing log level and confirming output changes.
- **SC-005**: Data persists across addon restarts — verified by creating an admin account, restarting the addon, and confirming the account still exists.
- **SC-006**: The existing test suite continues to pass with zero new failures introduced by the addon wiring changes.
- **SC-007**: The addon builds successfully for both amd64 and aarch64 architectures.
- **SC-008**: The application shuts down cleanly within 10 seconds of receiving a stop signal, with no database corruption.

## Assumptions

- The Home Assistant Supervisor writes addon configuration to the standard location (/data/options.json) before the addon starts, as documented in the HA addon development guide.
- The /data/ directory inside the addon container is persistent across restarts and upgrades, as guaranteed by the Home Assistant addon architecture.
- The addon base image used for this project provides a Python runtime compatible with the application's supported Python version range, as defined in the project metadata (for example, `pyproject.toml`).
- The existing application factory (`create_app()`) and database initialization functions (`create_db_engine()`, `init_db()`) are correct and complete — this feature wires them into the addon lifecycle without modifying their internal behavior.
- The existing session middleware configuration (`SessionConfig` with `idle_minutes` and `max_hours` fields) accepts the timeout values defined in the addon options schema.
- The project's package metadata (pyproject.toml) accurately lists all runtime dependencies needed for the application to function.
- Template and static file paths within the application use relative references that work regardless of the installation location inside the container.
- No database schema migration mechanism is needed for this initial wiring — the application creates tables from scratch on first run. Migration support is a separate future concern.
- Omada controller settings (host, credentials) are out of scope for the initial addon configuration schema and will be added when the Omada integration feature is wired up.
