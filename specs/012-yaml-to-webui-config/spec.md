# Feature Specification: Migrate Addon Configuration from YAML to Web UI

**Feature Branch**: `012-yaml-to-webui-config`
**Created**: 2025-07-18
**Status**: Draft
**Input**: User description: "Migrate addon configuration from YAML to web UI"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Omada Controller via Web UI (Priority: P1)

An admin wants to set up or change the Omada controller connection without editing YAML files and restarting the addon. They navigate to the admin web UI, enter the Omada controller URL, credentials, and site name, then save. The system validates the inputs, securely stores the credentials, and connects to the Omada controller — all without a restart.

**Why this priority**: The Omada controller is the core integration that enables the captive portal to function. Without a working Omada connection, no guest network access can be granted. Moving this to the web UI eliminates the most painful restart-required configuration change.

**Independent Test**: Can be fully tested by navigating to the Omada settings in the admin UI, entering controller details, saving, and verifying the system connects to the Omada controller without an addon restart.

**Acceptance Scenarios**:

1. **Given** the admin is on the Omada settings page, **When** they enter a valid controller URL, username, password, and site name and click Save, **Then** the settings are persisted and the system initiates a connection to the Omada controller.
2. **Given** the admin enters an invalid controller URL (e.g., not a valid URL format), **When** they click Save, **Then** the form displays a validation error and does not save.
3. **Given** the admin has a working Omada connection, **When** they update the controller URL to a different valid controller, **Then** the system disconnects from the old controller and connects to the new one.
4. **Given** the admin has saved Omada credentials, **When** they return to the Omada settings page, **Then** the password field shows a masked placeholder (not the actual password) and other fields show the saved values.
5. **Given** the Omada controller ID field is left empty, **When** the admin saves, **Then** the system auto-discovers the controller ID from the Omada API.
6. **Given** the admin toggles the SSL verification setting off, **When** they save, **Then** the system connects to the controller without validating its SSL certificate.

---

### User Story 2 - Automatic Migration of Existing YAML Settings (Priority: P2)

An admin upgrades the addon to the new version. They previously had Omada credentials, session timeouts, and a guest external URL configured in the YAML config. On first startup after the upgrade, the system automatically reads the existing YAML-based settings and migrates them into the database. The admin can then manage these settings entirely from the web UI going forward.

**Why this priority**: Without migration, upgrading would break the existing setup — the Omada connection would be lost and session settings would revert to defaults. This is critical for a smooth upgrade path and must work correctly on first startup.

**Independent Test**: Can be fully tested by configuring settings in YAML, upgrading to the new version, starting the addon, and verifying all migrated settings appear correctly in the web UI and the addon functions without manual reconfiguration.

**Acceptance Scenarios**:

1. **Given** the addon has Omada settings in the YAML config and no Omada settings in the database, **When** the addon starts, **Then** all Omada settings are migrated to the database and the Omada connection works.
2. **Given** session timeout values exist in the YAML config, **When** the addon starts after upgrade, **Then** the session idle timeout and max duration values appear in the web UI with the previously configured values.
3. **Given** a guest external URL is configured in YAML, **When** the addon starts after upgrade, **Then** the guest external URL appears in the web UI settings with the previously configured value.
4. **Given** settings have already been migrated to the database, **When** the addon restarts, **Then** the migration does not overwrite the database values (migration runs only once).
5. **Given** the YAML config has no optional settings configured (all defaults), **When** the addon starts after upgrade, **Then** the database is populated with the standard default values and the addon works normally.

---

### User Story 3 - Configure Session and Guest Portal Settings via Web UI (Priority: P3)

An admin wants to adjust how long guest sessions last or change the guest portal's external URL. They navigate to the Settings page in the admin UI, update the session idle timeout, session max duration, or guest external URL, and save. The changes take effect immediately without restarting.

**Why this priority**: Session and guest portal settings are changed less frequently than Omada settings, but they still benefit from a restart-free workflow. These integrate naturally into the existing Settings page alongside rate limiting and redirect settings.

**Independent Test**: Can be fully tested by navigating to the Settings page, modifying session timeout values and the guest external URL, saving, and verifying the new values take effect for new guest sessions.

**Acceptance Scenarios**:

1. **Given** the admin is on the Settings page, **When** they change the session idle timeout to 45 minutes and save, **Then** new guest sessions use a 45-minute idle timeout.
2. **Given** the admin sets the session max duration to 12 hours, **When** they save, **Then** new guest sessions have a maximum duration of 12 hours.
3. **Given** the admin enters a guest external URL, **When** they save, **Then** the guest portal uses the new external URL.
4. **Given** the admin enters an invalid session idle timeout (e.g., 0 or negative number), **When** they click Save, **Then** the form displays a validation error and does not save.
5. **Given** the admin clears the guest external URL field, **When** they save, **Then** the system uses the default empty value (auto-detection behavior).

---

### User Story 4 - YAML Config Simplified to Startup-Only Settings (Priority: P4)

An addon developer or advanced user reviews the YAML config schema after the migration. Only settings needed at startup remain: `log_level`, `debug_guest_portal`, `ha_base_url`, and `ha_token`. The removed settings no longer appear in the YAML schema, and the s6 run scripts no longer export environment variables for the migrated settings.

**Why this priority**: Cleaning up the YAML schema and run scripts prevents confusion about where settings are configured. Without this, users might set values in YAML that are silently ignored, leading to confusing behavior.

**Independent Test**: Can be fully tested by inspecting the addon config schema, confirming only four settings remain, and verifying the addon starts and functions correctly using only those YAML settings plus database-backed settings.

**Acceptance Scenarios**:

1. **Given** the updated addon config schema, **When** a user views the configuration options, **Then** only `log_level`, `debug_guest_portal`, `ha_base_url`, and `ha_token` are available.
2. **Given** the updated s6 run scripts, **When** the addon starts, **Then** environment variables for Omada settings, session settings, and guest external URL are no longer exported.
3. **Given** the updated settings resolution logic, **When** the application reads migrated settings, **Then** it resolves them from the database instead of addon options or environment variables.

---

### Edge Cases

- What happens when the database is empty on first startup with no YAML settings configured? The system should initialize all migrated settings to their documented default values.
- What happens when the admin saves Omada settings but the controller is unreachable? The settings should still be saved, and the system should display a connection error without losing the entered configuration.
- What happens when the database file is corrupted or deleted? The system should recreate the database and re-run migration from any remaining YAML values (or apply defaults).
- What happens when the admin submits the Omada form without changing the password field? The system should preserve the existing stored password rather than overwriting it with a blank or placeholder value.
- What happens when session idle timeout is set higher than session max duration? The system should allow this but the effective idle timeout would be capped by the max duration in practice (document this behavior).
- What happens if the addon starts with values in both YAML and the database for a migrated setting? The database value takes precedence (YAML values are only used for initial one-time migration).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a web UI form for configuring Omada controller settings (URL, username, password, site name, controller ID, SSL verification).
- **FR-002**: System MUST store the Omada password securely — not in plaintext. The stored password must be retrievable (reversible encryption) since it is used as a credential to authenticate with the Omada controller.
- **FR-003**: System MUST mask the Omada password in the web UI — never displaying the stored password value in form fields or page source.
- **FR-004**: System MUST trigger a reconnection to the Omada controller when Omada settings are saved with changed values.
- **FR-005**: System MUST auto-discover the Omada controller ID when the field is left empty and a valid controller URL and credentials are provided.
- **FR-006**: System MUST provide web UI fields for configuring session idle timeout (in minutes) and session max duration (in hours) on the Settings page.
- **FR-007**: System MUST provide a web UI field for configuring the guest portal external URL on the Settings page.
- **FR-008**: System MUST persist all migrated settings in the database so that changes take effect without restarting the addon.
- **FR-009**: System MUST validate all settings on the server side before persisting (URL format for URLs, positive integers for timeouts, boolean for SSL verification).
- **FR-010**: System MUST perform a one-time migration of existing YAML-configured values to the database on first startup after upgrade.
- **FR-011**: System MUST NOT overwrite database values during migration if they have already been migrated (migration is idempotent — runs only on first startup or when no database values exist).
- **FR-012**: System MUST preserve existing default values for all migrated settings (session idle timeout: 30 minutes, session max duration: 8 hours, site name: "Default", SSL verification: enabled).
- **FR-013**: System MUST remove migrated settings from the addon YAML config schema so they no longer appear as configurable options in the HA addon UI.
- **FR-014**: System MUST update s6 run scripts to stop exporting environment variables for migrated settings.
- **FR-015**: System MUST update the settings resolution logic to read migrated settings from the database instead of from addon options or environment variables.
- **FR-016**: System MUST display client-side validation feedback for form inputs (required fields, URL format, numeric ranges) before submission.
- **FR-017**: System MUST display success or error messages after saving settings, clearly indicating whether the save succeeded or what went wrong.
- **FR-018**: System MUST log an audit entry when Omada settings are changed (without logging the password value).
- **FR-019**: System MUST handle the case where the admin submits the Omada form without changing the password — preserving the existing stored password.

### Key Entities

- **OmadaConfig**: Stores the Omada controller connection settings — controller URL, username, encrypted password, site name, controller ID, and SSL verification preference. Singleton record (one Omada controller per addon instance).
- **PortalConfig (extended)**: The existing portal configuration record extended with session idle timeout, session max duration, and guest external URL fields. Singleton record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can configure all Omada controller settings through the web UI and establish a working Omada connection without restarting the addon.
- **SC-002**: Administrators can change session timeout and guest portal settings through the web UI, with changes taking effect for new sessions within 5 seconds of saving.
- **SC-003**: Existing users upgrading from YAML-based configuration have all their settings automatically preserved — zero manual reconfiguration required after upgrade.
- **SC-004**: The addon YAML configuration contains only 4 settings (log_level, debug_guest_portal, ha_base_url, ha_token) — down from the current 13.
- **SC-005**: The Omada password is never visible in plaintext in the web UI, page source, or database.
- **SC-006**: All configuration changes made through the web UI are persisted and survive addon restarts.
- **SC-007**: All migrated settings have complete test coverage — unit tests for data persistence, validation, and migration logic; integration tests for UI forms and setting application.

## Assumptions

- The existing `PortalConfig` model pattern (singleton record with id=1) is the preferred approach for storing configuration and will be extended or complemented for new settings.
- The admin web UI already has authentication and CSRF protection in place, which will be reused for the new settings forms.
- The Omada password requires reversible encryption (not one-way hashing) since the system must use it as a credential to authenticate against the Omada controller API.
- The existing audit logging infrastructure will be used to record configuration changes.
- Only one Omada controller can be configured per addon instance (matching the current YAML behavior).
- The migration reads from the addon options file (`/data/options.json`) or environment variables at startup — the same sources the current `AppSettings` class uses.
- Trusted proxy networks configuration remains on the existing Settings page via the `PortalConfig` model (unchanged by this feature).
- The web UI continues to use vanilla HTML/JS with Jinja2 templates — no JavaScript frameworks are introduced.
