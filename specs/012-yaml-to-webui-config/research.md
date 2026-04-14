# Research: Migrate Addon Configuration from YAML to Web UI

**Feature**: 012-yaml-to-webui-config
**Date**: 2025-07-18
**Status**: Complete

## R1: Reversible Password Encryption for Omada Credentials

### Context

The Omada controller password must be stored in the database but also decrypted at runtime to authenticate against the Omada controller API. The project constitution mandates Argon2 hashing for passwords, but Argon2 is a one-way hash — it cannot recover the original password. A deviation is required.

### Decision: Fernet Symmetric Encryption (via `cryptography` library)

### Rationale

- **Fernet** (from Python's `cryptography` package) provides authenticated encryption (AES-128-CBC + HMAC-SHA256) with a simple API.
- The `cryptography` package is already an indirect dependency via `httpx` → `httpcore` → `h11`, and is widely trusted.
- Fernet keys are 32-byte URL-safe base64-encoded strings, easily stored on the filesystem.
- The key file (`/data/.omada_key`) lives on the addon's persistent `/data` volume, surviving container rebuilds but accessible only to the addon process.
- If the key file is missing on startup, a new one is generated automatically — this means a fresh install or key loss will require re-entering the Omada password, which is acceptable.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Argon2 hashing | One-way; cannot recover password for API authentication |
| AES-GCM directly | More complex API, no advantage over Fernet for this use case |
| Store plaintext | Violates security requirements; password visible in DB dumps |
| Store in HA secrets | HA Supervisor doesn't provide a secrets API; addon options are plaintext in `/data/options.json` anyway |
| Python `keyring` | Requires system keyring service not available in s6-overlay container |

### Implementation Details

```python
# credential_encryption.py
from cryptography.fernet import Fernet

KEY_PATH = "/data/.omada_key"

def _load_or_create_key() -> bytes:
    """Load existing key or generate a new one."""
    try:
        with open(KEY_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as f:
            f.write(key)
        os.chmod(KEY_PATH, 0o600)
        return key

def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string, returning base64 ciphertext."""
    ...

def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a credential string from base64 ciphertext."""
    ...
```

---

## R2: Database Migration Strategy (YAML → DB)

### Context

Existing installations have Omada credentials, session timeouts, and guest URLs configured in YAML (`/data/options.json`) or environment variables. On upgrade, these must be seamlessly migrated to the database without losing configuration.

### Decision: One-time startup migration service with idempotency flag

### Rationale

- Migration runs during the app lifespan startup (after DB init, before route serving).
- Uses a sentinel record approach: if `OmadaConfig(id=1)` or extended `PortalConfig` fields already have non-default values, migration is skipped.
- Migration reads from `/data/options.json` directly (same source as `AppSettings.load()`), falling back to environment variables.
- This approach requires no schema versioning table — the presence of data is the migration flag.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Alembic migrations | Heavyweight for a single addon; the project uses lightweight `ALTER TABLE` migrations already |
| Version flag in separate table | Over-engineering; data presence is sufficient |
| Run migration as s6 init script | Would need Python + DB access before app starts; complicates startup order |
| Prompt user to re-enter settings | Poor UX; violates SC-003 (zero manual reconfiguration) |

### Migration Logic

1. On startup, after `init_db()`, call `migrate_yaml_to_db(settings, db_session)`.
2. For Omada settings: if `OmadaConfig` table has no row with id=1, create one from `AppSettings` values (encrypting password).
3. For session/guest settings: if `PortalConfig.session_idle_minutes` is still at default AND AppSettings has a non-default value from YAML, update. Same for `session_max_hours` and `guest_external_url`.
4. Log all migrated values (redacting password).
5. On subsequent starts, existing DB rows prevent re-migration.

---

## R3: OmadaConfig Model Design

### Context

Omada controller settings are currently spread across `AppSettings` fields and environment variables. They need a dedicated database model.

### Decision: New `OmadaConfig` SQLModel with singleton pattern (id=1)

### Rationale

- Follows the existing `PortalConfig` singleton pattern — single record with `id=1`.
- Stores encrypted password (Fernet ciphertext), not plaintext.
- Includes all six Omada fields: `controller_url`, `username`, `encrypted_password`, `site_name`, `controller_id`, `verify_ssl`.
- Registered with SQLModel metadata in `database.py` for automatic table creation.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Extend PortalConfig with Omada fields | PortalConfig is guest portal config; mixing concerns violates single responsibility |
| Key-value settings table | Loses type safety and validation; harder to query |
| JSON blob in PortalConfig | No field-level validation; migration complexity |

---

## R4: Settings Resolution Architecture Change

### Context

Currently, `AppSettings.load()` resolves ALL settings from YAML → env vars → defaults. After migration, nine settings move to the database. The resolution logic must change.

### Decision: Split settings into two categories

### Rationale

**Category A — Startup-only (remain in AppSettings)**:
- `log_level` — needed before DB is available
- `debug_guest_portal` — needed at app construction time
- `ha_base_url` — needed to create HAClient before DB
- `ha_token` — needed to create HAClient before DB
- `db_path` — needed to initialize the database itself

**Category B — Runtime (move to database)**:
- `omada_controller_url` → `OmadaConfig.controller_url`
- `omada_username` → `OmadaConfig.username`
- `omada_password` → `OmadaConfig.encrypted_password`
- `omada_site_name` → `OmadaConfig.site_name`
- `omada_controller_id` → `OmadaConfig.controller_id`
- `omada_verify_ssl` → `OmadaConfig.verify_ssl`
- `session_idle_minutes` → `PortalConfig.session_idle_minutes`
- `session_max_hours` → `PortalConfig.session_max_hours`
- `guest_external_url` → `PortalConfig.guest_external_url`

### Approach

- `AppSettings` retains Category A fields only. Category B fields remain on the class temporarily for migration reads (so `AppSettings.load()` can still read `/data/options.json` for migration), but are not used at runtime after migration.
- `build_omada_config()` changes to read from `OmadaConfig` DB model instead of `AppSettings`.
- Session config is read from `PortalConfig` at startup and when settings are updated.
- The `omada_configured` property moves to `OmadaConfig` model.

---

## R5: Omada Controller Reconnection on Settings Change

### Context

When an admin saves new Omada settings via the web UI, the system must establish (or re-establish) the connection to the Omada controller without restarting the addon.

### Decision: Store `omada_config` dict in `app.state` and refresh on save

### Rationale

- Current architecture already stores `app.state.omada_config` (a dict) at startup.
- On Omada settings save: rebuild the config dict from the updated `OmadaConfig` model, replace `app.state.omada_config`.
- The `OmadaAdapter` dependency (`get_omada_adapter`) already reads from `app.state.omada_config` on every request — no additional wiring needed.
- Auto-discovery of `controller_id` happens during the save operation (async), not on every request.
- Both admin and guest apps need the updated config. The guest app runs as a separate process, so it reads from the DB independently. A simple "reload on next request" pattern works since the guest adapter re-reads `app.state.omada_config` which can be refreshed periodically or on-demand.

### Guest App Synchronization

- The guest app currently reads Omada config at startup only.
- After this feature, the guest app will read `OmadaConfig` from DB at startup and rebuild `app.state.omada_config`.
- For live updates without restart: the guest app's lifespan will also check the DB, or a lightweight poll/signal mechanism can be added. For MVP, a restart of the guest service via s6 is acceptable since Omada config changes are infrequent.

---

## R6: Admin UI Navigation for Omada Settings

### Context

The admin UI has a top navigation bar with: Dashboard, Grants, Vouchers, Integrations, Settings. A new "Omada Settings" page needs to be accessible.

### Decision: Add "Omada" link to the navigation bar between "Integrations" and "Settings"

### Rationale

- The navigation bar is duplicated in each template (no shared base template). Each admin template includes the `<nav>` block.
- Adding "Omada" between "Integrations" and "Settings" groups network-related items together.
- The new page follows the same template structure: standalone HTML with nav, CSRF, flash messages.
- URL: `/admin/omada-settings/`

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Sub-tab under Settings | Settings page would become too long; Omada is a distinct concern |
| Accordion/collapsible sections | Breaks consistency with existing flat-page pattern |
| Modal dialog | Too complex for 6+ form fields; no existing modal pattern |

---

## R7: Password Field Handling in Omada Form

### Context

When the admin returns to the Omada settings page, the password field must show a masked placeholder — never the actual password. When saving, if the password field is unchanged (still shows placeholder), the existing encrypted password must be preserved.

### Decision: Sentinel placeholder pattern

### Rationale

- On GET: password field shows `••••••••` (8 bullet characters) as placeholder text via HTML `placeholder` attribute. The `value` attribute is empty.
- A hidden field `password_changed` tracks whether the user modified the password field (set by JavaScript `input` event listener).
- On POST: if `password_changed` is "false" or password is empty, preserve existing encrypted password. If `password_changed` is "true" and password is non-empty, encrypt and store the new password.
- This prevents accidental password clearing and never sends the real password to the browser.

---

## R8: Session/Guest Settings Integration into Existing Portal Settings Page

### Context

Session idle timeout, session max duration, and guest external URL need UI controls. These are operationally similar to the existing rate limiting and redirect settings.

### Decision: Add new form sections to the existing Portal Settings page

### Rationale

- The existing Portal Settings page (`/admin/portal-settings/`) already handles PortalConfig.
- Adding "Session Timeouts" and "Guest Portal" sections follows the established form-section pattern.
- No new page needed — fewer navigation changes.
- The POST handler already handles PortalConfig updates — just add the new fields.

---

## R9: `cryptography` Dependency Addition

### Context

The `cryptography` package is needed for Fernet encryption of the Omada password.

### Decision: Add `cryptography` as an explicit dependency

### Rationale

- While `cryptography` may already be an indirect dependency, it should be declared explicitly since we import from it directly.
- Add to `pyproject.toml` under `[project.dependencies]`.
- Lock with `uv lock`.
- The package is well-maintained, has pre-built wheels for amd64/aarch64, and adds minimal overhead.
