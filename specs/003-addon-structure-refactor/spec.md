SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Restructure Addon to Standard HA Patterns

**Feature Branch**: `003-addon-structure-refactor`
**Created**: 2025-07-15
**Status**: Draft
**Input**: User description: "Restructure captive-portal HA addon to match standard HA addon patterns"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — HA Supervisor Builds and Starts the Addon (Priority: P1)

A Home Assistant user adds the captive-portal repository to their HA instance and installs the addon. The HA Supervisor clones the repository, uses the `addon/` directory as its build context, builds the container image, and starts the addon. The addon starts successfully, becomes reachable through HA's admin panel, and serves the captive portal web interface.

**Why this priority**: This is the fundamental reason for the restructure. Today, the addon cannot build under HA Supervisor because the Dockerfile references files outside the `addon/` build context. Nothing else matters if the addon cannot build and run.

**Independent Test**: Can be fully tested by adding the repository URL to a Home Assistant instance, installing the addon, and verifying it starts and serves its web interface on the configured port.

**Acceptance Scenarios**:

1. **Given** the repository is added to HA as a custom addon repository, **When** the user clicks "Install" on the Captive Portal addon, **Then** the addon builds to completion without errors.
2. **Given** the addon has been installed, **When** the user clicks "Start," **Then** the addon reaches a "running" state and the admin panel link becomes active.
3. **Given** the addon is running, **When** the user opens the admin panel, **Then** the captive portal web interface loads and responds to requests.
4. **Given** the addon is running, **When** the existing `/health` endpoint is accessed (its path is unchanged by this restructure), **Then** it returns a healthy status.

---

### User Story 2 — Developer Runs Tests from the Repo Root (Priority: P2)

A developer clones the repository, installs development dependencies from the root, and runs the full test suite. The full existing test suite (currently 441 tests) passes without modification to the test assertions or application logic. The developer can iterate on code changes and re-run tests using the same workflow they use today.

**Why this priority**: Maintaining the development workflow ensures contributors can continue working on the project without disruption. If tests break or the development experience degrades, the restructure creates more problems than it solves.

**Independent Test**: Can be fully tested by cloning the repository, running the standard test command from the repo root, and verifying the full test suite passes with no failures.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository on the feature branch, **When** the developer installs dependencies and runs the full test suite from the repo root, **Then** the full existing test suite passes with no failures.
2. **Given** the source code has been relocated into the addon directory, **When** the developer imports any captive-portal module in a test file, **Then** the import resolves correctly.
3. **Given** the root project configuration has been updated, **When** the developer runs linting and type-checking tools from the repo root, **Then** they analyze the source code at its new location without errors.

---

### User Story 3 — Developer Builds the Addon Image Locally (Priority: P3)

A developer builds the addon container image locally to verify their changes before pushing. They run a container build command targeting `addon/` as the build context. The build completes successfully, and the resulting image can be started and tested outside of Home Assistant.

**Why this priority**: Local container builds are essential for rapid iteration and troubleshooting without needing a full HA instance. This is the developer's inner loop for addon-specific changes.

**Independent Test**: Can be fully tested by running a container build command against the `addon/` directory and verifying the resulting image starts and responds on the expected port.

**Acceptance Scenarios**:

1. **Given** the addon directory contains all required source files and configuration, **When** the developer runs a container build targeting `addon/` as the build context, **Then** the build completes successfully.
2. **Given** a locally built container image, **When** the developer starts the container with required environment variables, **Then** the captive portal application starts and listens on port 8080.
3. **Given** a running local container, **When** the developer accesses the health endpoint, **Then** it responds with a healthy status.

---

### User Story 4 — Addon Restarts After a Crash (Priority: P4)

The captive portal application process crashes unexpectedly due to an unhandled error. The process supervision system detects the exit, logs the event, and automatically restarts the application process. The addon returns to a healthy running state without manual intervention.

**Why this priority**: Process supervision via s6-overlay is the standard HA addon pattern for reliability. Without it, a crash leaves the addon dead until the user manually restarts it, which is a poor experience for a network access service.

**Independent Test**: Can be fully tested by sending a kill signal to the application process inside the running container and verifying it is restarted automatically.

**Acceptance Scenarios**:

1. **Given** the addon is running under process supervision, **When** the application process exits unexpectedly, **Then** the supervisor restarts it automatically.
2. **Given** the addon has been restarted after a crash, **When** a user accesses the web interface, **Then** the portal is responsive and functional.

---

### User Story 5 — Addon Builds on Multiple Architectures (Priority: P5)

A user with an ARM-based Home Assistant device (e.g., Raspberry Pi with aarch64) installs the addon. The HA Supervisor selects the correct architecture-specific base image and builds the addon container. For this feature, the addon builds and runs correctly on hosts using the amd64 or aarch64 architectures.

**Why this priority**: Multi-architecture support (amd64 and aarch64) is required for broadly usable HA addon distribution. Many HA users run on Raspberry Pi (aarch64) or other ARM devices. Without this, the addon is limited to amd64 users only; support for additional architectures (such as armv7) is out of scope for this feature.

**Independent Test**: Can be fully tested by verifying the build configuration specifies correct base images for each supported architecture and that the container build succeeds when targeting different architectures.

**Acceptance Scenarios**:

1. **Given** the build configuration lists supported architectures, **When** the HA Supervisor builds for amd64, **Then** it uses the correct amd64-specific base image and succeeds.
2. **Given** the build configuration lists supported architectures, **When** the HA Supervisor builds for aarch64, **Then** it uses the correct aarch64-specific base image and succeeds.
3. **Given** the addon config declares architecture support, **When** a user on an unsupported architecture tries to install, **Then** the addon is not available for installation.

---

### User Story 6 — All New and Modified Files Have License Headers (Priority: P6)

A compliance reviewer checks the repository and verifies that every new or modified file created during this restructure includes proper SPDX license headers. The project's REUSE compliance status remains valid or improves.

**Why this priority**: The project already uses SPDX headers and REUSE.toml for license compliance. New files introduced by this restructure must follow the same standard to maintain compliance.

**Independent Test**: Can be fully tested by running a REUSE compliance check tool against the repository and verifying it reports no missing headers.

**Acceptance Scenarios**:

1. **Given** new files are created during the restructure (build config, addon package config, service definitions), **When** a license compliance check is run, **Then** all new files have valid SPDX headers.
2. **Given** existing files are moved or modified, **When** a license compliance check is run, **Then** the moved/modified files retain their SPDX headers.

---

### Edge Cases

- What happens if the addon is built with a stale dependency lock file that does not match the package requirements? The build must fail clearly rather than silently using wrong versions.
- What happens if the addon build context is missing the source directory? The container build must fail with a clear error during the COPY step, not at runtime.
- What happens if the process supervision service definition has incorrect permissions? The addon must report a startup failure rather than silently doing nothing.
- What happens if a developer runs tests but has not installed dependencies at the new source path? The test runner must produce an import error pointing to the correct location.
- What happens if the addon config declares an architecture not present in the build config? The HA Supervisor must not offer the addon for installation on that architecture.

## Requirements *(mandatory)*

### Functional Requirements

#### Source Code Relocation

- **FR-001**: All application source code MUST reside within the `addon/` directory so that the HA Supervisor build context contains everything needed for the container build.
- **FR-002**: The source code directory structure within the addon MUST preserve the existing module hierarchy so that all internal imports remain valid.
- **FR-003**: All static assets (HTML templates, CSS themes) MUST be relocated alongside the source code within the addon directory.

#### Addon Build Configuration

- **FR-004**: The addon MUST include a build configuration file that maps each supported architecture to its corresponding base container image.
- **FR-005**: The addon MUST support at minimum the amd64 and aarch64 architectures, matching the current addon config.
- **FR-006**: The addon container build MUST use a reproducible, lock-file-based dependency installation to ensure deterministic builds.
- **FR-007**: The addon container MUST use a modern dependency management tool (uv) instead of pip for faster, more reliable builds.

#### Addon Metadata Configuration

- **FR-008**: The addon metadata configuration MUST be provided in YAML format, replacing the current JSON format, to follow HA addon conventions.
- **FR-009**: The addon metadata MUST preserve all existing configuration options (log level, session idle timeout, session max duration).
- **FR-010**: The addon metadata MUST preserve the existing port mapping (8080/tcp), admin panel setting, web UI URL template, and HA API access flag.

#### Process Supervision

- **FR-011**: The addon MUST use the HA standard process supervision framework (s6-overlay) to manage the application process lifecycle.
- **FR-012**: The service definition MUST be configured as a long-running service that is automatically restarted if the process exits.
- **FR-013**: The service run script MUST start the application server on the configured port (8080) binding to all interfaces.

#### Addon Package Configuration

- **FR-014**: The addon directory MUST contain its own package configuration file that defines the addon as a self-contained installable package.
- **FR-015**: The addon package configuration MUST use the hatchling build backend, following the reference implementation pattern.
- **FR-016**: The addon package configuration MUST list all runtime dependencies required by the captive portal application.

#### Development Workflow Preservation

- **FR-017**: The root-level project configuration MUST be updated to reference source code at its new location within the addon directory.
- **FR-018**: The full existing test suite MUST pass from the repository root without changes to test logic or assertions.
- **FR-019**: Development tooling (linting, type-checking, coverage) MUST continue to work from the repository root against the relocated source.

#### Dependency Lock File

- **FR-020**: A dependency lock file MUST be present in the addon directory to enable frozen, reproducible dependency installation during container builds.

#### License Compliance

- **FR-021**: All newly created files MUST include SPDX license headers with the copyright holder "Andrew Grimberg" and the Apache-2.0 license identifier.
- **FR-022**: All relocated files MUST retain their existing SPDX license headers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The addon container image builds to completion from the `addon/` directory as build context with zero errors.
- **SC-002**: The full existing test suite passes from the repository root after the restructure, with zero test failures and zero test modifications.
- **SC-003**: The addon starts under HA Supervisor and reaches a running state within 60 seconds of the start command.
- **SC-004**: The captive portal web interface responds to requests within 5 seconds of the addon reaching running state.
- **SC-005**: When the application process is terminated, the process supervisor restarts it and the service is available again within 30 seconds.
- **SC-006**: The addon builds successfully for both amd64 and aarch64 architectures.
- **SC-007**: A REUSE/SPDX compliance check reports no missing license headers on any new or modified file.
- **SC-008**: A developer can go from a fresh clone to running tests in under 5 minutes following the existing workflow.

## Assumptions

- The existing test suite (currently 441 tests) is the authoritative measure of application correctness; if all tests pass, the application behavior is preserved.
- The HA Supervisor uses only the contents of the `addon/` directory as its build context. Files outside `addon/` are not available during the container build.
- The reference implementation (rentalsync-bridge) represents the current best practice for HA addon structure and can be used as the pattern to follow.
- The s6-overlay process supervisor is provided by the HA base container images and does not need to be installed separately.
- The application's runtime behavior, API routes, and user-facing interfaces are unchanged by this restructure; only file locations, build tooling, and process management change.
- The root-level project configuration is used only for development purposes (running tests, linting, type-checking) and is not involved in the addon build process.
- The armv7 architecture is out of scope for this feature; only amd64 and aarch64 are targeted. armv7 may be added in a future iteration.
- The dependency lock file in the addon directory may be a copy of or symlink to the root lock file, as long as the container build can consume it.
- The current JSON-format addon config contains the complete and correct set of metadata; the YAML conversion is a format change only, with no semantic changes needed.
