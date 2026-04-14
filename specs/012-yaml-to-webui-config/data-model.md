# Data Model: Migrate Addon Configuration from YAML to Web UI

**Feature**: 012-yaml-to-webui-config
**Date**: 2025-07-18

## Entity Overview

```
┌─────────────────┐       ┌─────────────────────┐
│   OmadaConfig   │       │    PortalConfig      │
│   (NEW model)   │       │  (EXTENDED model)    │
│   singleton=1   │       │    singleton=1       │
├─────────────────┤       ├─────────────────────┤
│ controller_url  │       │ success_redirect_url │ (existing)
│ username        │       │ rate_limit_attempts  │ (existing)
│ encrypted_pass  │       │ rate_limit_window_s  │ (existing)
│ site_name       │       │ redirect_to_orig_url │ (existing)
│ controller_id   │       │ trusted_proxy_nets   │ (existing)
│ verify_ssl      │       │ session_idle_minutes │ ← NEW
└─────────────────┘       │ session_max_hours    │ ← NEW
                          │ guest_external_url   │ ← NEW
                          └─────────────────────┘

┌─────────────────┐
│   AppSettings   │
│  (SIMPLIFIED)   │
├─────────────────┤
│ log_level       │ (retained)
│ db_path         │ (retained)
│ ha_base_url     │ (retained)
│ ha_token        │ (retained)
│ debug_guest_..  │ (retained)
│ ─── removed ─── │
│ session_idle_m.  │ → PortalConfig
│ session_max_h.   │ → PortalConfig
│ guest_ext_url    │ → PortalConfig
│ omada_ctrl_url   │ → OmadaConfig
│ omada_username   │ → OmadaConfig
│ omada_password   │ → OmadaConfig
│ omada_site_name  │ → OmadaConfig
│ omada_ctrl_id    │ → OmadaConfig
│ omada_verify_ssl │ → OmadaConfig
└─────────────────┘
```

## New Entity: OmadaConfig

**Table name**: `omada_config`
**Pattern**: Singleton (id=1, same as PortalConfig)
**File**: `addon/src/captive_portal/models/omada_config.py`

| Field | Type | Default | Constraints | Notes |
|-------|------|---------|-------------|-------|
| `id` | `int` | `1` | Primary key | Singleton — always 1 |
| `controller_url` | `str` | `""` | max_length=2048 | Omada controller URL (http/https) |
| `username` | `str` | `""` | max_length=255 | Omada hotspot operator username |
| `encrypted_password` | `str` | `""` | max_length=1024 | Fernet-encrypted password ciphertext |
| `site_name` | `str` | `"Default"` | max_length=255 | Omada site name |
| `controller_id` | `str` | `""` | max_length=64 | Hex controller ID (auto-discovered if empty) |
| `verify_ssl` | `bool` | `True` | — | SSL certificate verification toggle |

### Validation Rules

- `controller_url`: Must be valid `http://` or `https://` URL, or empty string
- `username`: Free-form string, trimmed
- `encrypted_password`: Base64-encoded Fernet ciphertext (not user-validated; system-managed)
- `site_name`: Free-form string, trimmed; defaults to "Default"
- `controller_id`: Must match `^[a-fA-F0-9]{12,64}$` if non-empty, or empty for auto-discovery
- `verify_ssl`: Boolean

### Computed Property

```python
@property
def omada_configured(self) -> bool:
    """True when URL, username, and encrypted_password are all non-empty."""
    return bool(
        self.controller_url.strip()
        and self.username.strip()
        and self.encrypted_password.strip()
    )
```

### SQLModel Definition

```python
class OmadaConfig(SQLModel, table=True):
    __tablename__ = "omada_config"
    model_config = {"validate_assignment": True}

    id: int = Field(default=1, primary_key=True)
    controller_url: str = Field(default="", max_length=2048)
    username: str = Field(default="", max_length=255)
    encrypted_password: str = Field(default="", max_length=1024)
    site_name: str = Field(default="Default", max_length=255)
    controller_id: str = Field(default="", max_length=64)
    verify_ssl: bool = Field(default=True)
```

---

## Extended Entity: PortalConfig

**Table name**: `portal_config` (unchanged)
**File**: `addon/src/captive_portal/models/portal_config.py`

### New Fields (added via lightweight migration)

| Field | Type | Default | Constraints | Notes |
|-------|------|---------|-------------|-------|
| `session_idle_minutes` | `int` | `30` | ge=1, le=1440 | Guest session idle timeout in minutes |
| `session_max_hours` | `int` | `8` | ge=1, le=168 | Guest session max duration in hours |
| `guest_external_url` | `str` | `""` | max_length=2048 | Guest portal external URL for captive detection |

### Validation Rules

- `session_idle_minutes`: Integer 1–1440 (1 minute to 24 hours)
- `session_max_hours`: Integer 1–168 (1 hour to 7 days)
- `guest_external_url`: Valid `http://` or `https://` URL with no query/fragment, or empty string

### Updated SQLModel Definition

```python
class PortalConfig(SQLModel, table=True):
    __tablename__ = "portal_config"
    model_config = {"validate_assignment": True}

    # Existing fields (unchanged)
    id: int = Field(default=1, primary_key=True)
    success_redirect_url: str = Field(default="/guest/welcome", max_length=2048)
    rate_limit_attempts: int = Field(default=5, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    redirect_to_original_url: bool = Field(default=True)
    trusted_proxy_networks: Optional[str] = Field(
        default='["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]',
        sa_column=Column(TEXT),
    )

    # NEW fields (added by this feature)
    session_idle_minutes: int = Field(default=30, ge=1, le=1440)
    session_max_hours: int = Field(default=8, ge=1, le=168)
    guest_external_url: str = Field(default="", max_length=2048)
```

### Database Migration

New columns added via lightweight `ALTER TABLE` migration in `database.py`:

```python
def _migrate_portal_config_session_fields(engine: Engine) -> None:
    """Add session and guest URL columns to portal_config table."""
    insp = inspect(engine)
    if "portal_config" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("portal_config")}
    with engine.begin() as conn:
        if "session_idle_minutes" not in columns:
            conn.execute(text(
                "ALTER TABLE portal_config ADD COLUMN session_idle_minutes INTEGER DEFAULT 30"
            ))
        if "session_max_hours" not in columns:
            conn.execute(text(
                "ALTER TABLE portal_config ADD COLUMN session_max_hours INTEGER DEFAULT 8"
            ))
        if "guest_external_url" not in columns:
            conn.execute(text(
                "ALTER TABLE portal_config ADD COLUMN guest_external_url VARCHAR(2048) DEFAULT ''"
            ))
```

---

## Simplified Entity: AppSettings

**File**: `addon/src/captive_portal/config/settings.py`

### Fields After Migration

| Field | Retained | Resolution Source |
|-------|----------|-------------------|
| `log_level` | ✅ | YAML → env → default |
| `db_path` | ✅ | env → default |
| `ha_base_url` | ✅ | YAML → env → default |
| `ha_token` | ✅ | SUPERVISOR_TOKEN → env → default |
| `debug_guest_portal` | ✅ | YAML → env → default |
| `session_idle_minutes` | ❌ removed | → `PortalConfig` DB |
| `session_max_hours` | ❌ removed | → `PortalConfig` DB |
| `guest_external_url` | ❌ removed | → `PortalConfig` DB |
| `omada_controller_url` | ❌ removed | → `OmadaConfig` DB |
| `omada_username` | ❌ removed | → `OmadaConfig` DB |
| `omada_password` | ❌ removed | → `OmadaConfig` DB |
| `omada_site_name` | ❌ removed | → `OmadaConfig` DB |
| `omada_controller_id` | ❌ removed | → `OmadaConfig` DB |
| `omada_verify_ssl` | ❌ removed | → `OmadaConfig` DB |

**Note**: During the migration phase, `AppSettings` temporarily retains Category B fields so `AppSettings.load()` can read YAML values for the one-time migration. After migration runs, these fields are not used at runtime. They can optionally be removed from `AppSettings` entirely once migration support is no longer needed (future cleanup).

---

## New Module: Credential Encryption

**File**: `addon/src/captive_portal/security/credential_encryption.py`

### Interface

```python
def encrypt_credential(plaintext: str, key_path: str = "/data/.omada_key") -> str:
    """Encrypt a credential string using Fernet.

    Args:
        plaintext: The credential to encrypt.
        key_path: Path to the Fernet key file.

    Returns:
        Base64-encoded ciphertext string.

    Raises:
        ValueError: If plaintext is empty.
    """

def decrypt_credential(ciphertext: str, key_path: str = "/data/.omada_key") -> str:
    """Decrypt a Fernet-encrypted credential.

    Args:
        ciphertext: Base64-encoded ciphertext.
        key_path: Path to the Fernet key file.

    Returns:
        Decrypted plaintext string.

    Raises:
        ValueError: If ciphertext is empty or invalid.
        cryptography.fernet.InvalidToken: If key is wrong or data corrupted.
    """
```

### Key Management

- Key file location: `/data/.omada_key` (persistent addon volume)
- Permissions: `0o600` (owner read/write only)
- Auto-generated on first use if missing
- Key loss = password re-entry required (acceptable trade-off)

---

## New Service: Config Migration

**File**: `addon/src/captive_portal/services/config_migration.py`

### Interface

```python
async def migrate_yaml_to_db(
    settings: AppSettings,
    session: Session,
    key_path: str = "/data/.omada_key",
) -> MigrationResult:
    """One-time migration of YAML/env settings to database.

    Args:
        settings: AppSettings loaded from YAML/env (pre-migration sources).
        session: Database session.
        key_path: Path to encryption key file.

    Returns:
        MigrationResult with counts of migrated fields.
    """
```

### MigrationResult

```python
class MigrationResult(BaseModel):
    omada_migrated: bool = False
    session_fields_migrated: int = 0
    guest_url_migrated: bool = False
    skipped_reason: str | None = None
```

### Idempotency Rules

1. If `OmadaConfig(id=1)` exists in DB → skip Omada migration
2. If `PortalConfig.session_idle_minutes != 30` (non-default) → skip session field migration
3. If `PortalConfig.guest_external_url != ""` → skip guest URL migration
4. Each category is independent — partial migration is valid

---

## State Transitions

### Omada Connection State

```
[No Config] ──save──→ [Config Saved] ──connect──→ [Connected]
                           │                          │
                           │                     ──error──→ [Connection Error]
                           │                          │
                      ──update──→ [Config Saved] ──reconnect──→ [Connected]
```

- Settings are always persisted regardless of connection outcome
- Connection errors are displayed but don't prevent saving
- The Omada adapter reads `app.state.omada_config` on each request

### Migration State

```
[First Startup] ──no DB record──→ [Read YAML] ──write DB──→ [Migrated]
                                                                │
[Subsequent Startup] ──DB record exists──→ [Skip Migration] ────┘
```

---

## Relationships

- `OmadaConfig` → standalone singleton, no FK relationships
- `PortalConfig` → standalone singleton (extended), no FK relationships
- `AppSettings` → read-only at startup, feeds migration service
- `OmadaConfig.encrypted_password` ↔ `credential_encryption` module (encrypt/decrypt)
- `OmadaConfig` → consumed by `build_omada_config()` → `app.state.omada_config`
- `PortalConfig.session_*` → consumed by `SessionConfig` at startup and on settings update
