# Contract: Portal Settings Extensions

**Feature**: 012-yaml-to-webui-config
**Endpoint prefix**: `/admin/portal-settings` (existing)
**Authentication**: Admin role required (session-based)

## Changes to Existing GET `/admin/portal-settings/`

### Additional Context Variables

| Variable | Type | Description |
|----------|------|-------------|
| `config.session_idle_minutes` | `int` | Current session idle timeout (1-1440) |
| `config.session_max_hours` | `int` | Current session max duration (1-168) |
| `config.guest_external_url` | `str` | Current guest portal external URL |

### Additional Form Sections (appended to existing template)

#### Section: Session Timeouts

| Field | HTML Type | Source | Validation |
|-------|-----------|--------|------------|
| `session_idle_minutes` | `<input type="number" min="1" max="1440">` | `config.session_idle_minutes` | Integer 1–1440 |
| `session_max_hours` | `<input type="number" min="1" max="168">` | `config.session_max_hours` | Integer 1–168 |

#### Section: Guest Portal

| Field | HTML Type | Source | Validation |
|-------|-----------|--------|------------|
| `guest_external_url` | `<input type="url">` | `config.guest_external_url` | Valid URL or empty |

---

## Changes to Existing POST `/admin/portal-settings/`

### Additional Form Parameters

| Parameter | Type | Required | Validation |
|-----------|------|----------|------------|
| `session_idle_minutes` | `int` | Yes | 1 ≤ value ≤ 1440 |
| `session_max_hours` | `int` | Yes | 1 ≤ value ≤ 168 |
| `guest_external_url` | `str` | No | Valid http/https URL or empty |

### Additional Server-Side Validation

1. `session_idle_minutes` must be integer between 1 and 1440
2. `session_max_hours` must be integer between 1 and 168
3. `guest_external_url` must be valid http/https URL (no query params, no fragment) or empty string

### Additional Post-Save Actions

1. Persist new session/guest fields to `PortalConfig`
2. Update `app.state.session_config` with new `SessionConfig(idle_minutes=..., max_hours=...)`
3. Update `app.state.guest_external_url` (if guest app reads from admin app state, or handled separately)

### Extended Audit Log Entry

```json
{
  "action": "portal_config.update",
  "target_type": "portal_config",
  "target_id": "1",
  "metadata": {
    "rate_limit_attempts": 5,
    "rate_limit_window_seconds": 60,
    "redirect_to_original_url": true,
    "session_idle_minutes": 45,
    "session_max_hours": 12,
    "guest_external_url": "https://guest.example.com"
  }
}
```

---

## Changes to Existing API: GET `/api/admin/portal-config`

### Extended Response Model

```python
class PortalConfigResponse(BaseModel):
    id: int
    success_redirect_url: str
    rate_limit_attempts: int
    rate_limit_window_seconds: int
    redirect_to_original_url: bool
    trusted_proxy_networks: list[str]
    # NEW fields
    session_idle_minutes: int
    session_max_hours: int
    guest_external_url: str
```

---

## Changes to Existing API: PUT `/api/admin/portal-config`

### Extended Update Model

```python
class PortalConfigUpdate(BaseModel):
    success_redirect_url: str | None = None
    rate_limit_attempts: int | None = None
    rate_limit_window_seconds: int | None = None
    redirect_to_original_url: bool | None = None
    trusted_proxy_networks: list[str] | None = None
    # NEW fields
    session_idle_minutes: int | None = None
    session_max_hours: int | None = None
    guest_external_url: str | None = None
```

---

## Client-Side Validation Updates

**File**: `admin-portal-settings.js`

### Additional Validation Rules

```javascript
// Session idle timeout: 1-1440 minutes
const idleMinutes = parseInt(document.getElementById("session_idle_minutes").value);
if (isNaN(idleMinutes) || idleMinutes < 1 || idleMinutes > 1440) {
    alert("Session idle timeout must be between 1 and 1440 minutes.");
    return false;
}

// Session max duration: 1-168 hours
const maxHours = parseInt(document.getElementById("session_max_hours").value);
if (isNaN(maxHours) || maxHours < 1 || maxHours > 168) {
    alert("Session max duration must be between 1 and 168 hours.");
    return false;
}

// Guest external URL: valid URL or empty
const guestUrl = document.getElementById("guest_external_url").value.trim();
if (guestUrl && !isValidUrl(guestUrl)) {
    alert("Guest external URL must be a valid HTTP or HTTPS URL.");
    return false;
}
```

---

## YAML Schema Changes

### Before (13 settings)

```yaml
schema:
  log_level: "list(trace|debug|info|notice|warning|error|fatal)?"
  session_idle_timeout: "int(1,)?"
  session_max_duration: "int(1,)?"
  guest_external_url: "url?"
  ha_base_url: "url?"
  ha_token: "str?"
  omada_controller_url: "url?"
  omada_username: "str?"
  omada_password: "password?"
  omada_site_name: "str?"
  omada_controller_id: "str?"
  omada_verify_ssl: "bool?"
  debug_guest_portal: "bool?"
```

### After (4 settings)

```yaml
schema:
  log_level: "list(trace|debug|info|notice|warning|error|fatal)?"
  ha_base_url: "url?"
  ha_token: "str?"
  debug_guest_portal: "bool?"
```

### Removed Settings

| Setting | Moved To |
|---------|----------|
| `session_idle_timeout` | `PortalConfig.session_idle_minutes` (DB + Web UI) |
| `session_max_duration` | `PortalConfig.session_max_hours` (DB + Web UI) |
| `guest_external_url` | `PortalConfig.guest_external_url` (DB + Web UI) |
| `omada_controller_url` | `OmadaConfig.controller_url` (DB + Web UI) |
| `omada_username` | `OmadaConfig.username` (DB + Web UI) |
| `omada_password` | `OmadaConfig.encrypted_password` (DB + Web UI) |
| `omada_site_name` | `OmadaConfig.site_name` (DB + Web UI) |
| `omada_controller_id` | `OmadaConfig.controller_id` (DB + Web UI) |
| `omada_verify_ssl` | `OmadaConfig.verify_ssl` (DB + Web UI) |

---

## s6 Run Script Changes

### `captive-portal/run` — Remove These Exports

```bash
# REMOVE: CP_OMADA_CONTROLLER_URL, CP_OMADA_USERNAME, CP_OMADA_PASSWORD
# REMOVE: CP_OMADA_SITE_NAME, CP_OMADA_CONTROLLER_ID, CP_OMADA_VERIFY_SSL
# KEEP:   CP_DEBUG_GUEST_PORTAL (retained in AppSettings)
```

### `captive-portal-guest/run` — Remove These Exports

```bash
# REMOVE: CP_GUEST_EXTERNAL_URL
# REMOVE: CP_OMADA_CONTROLLER_URL, CP_OMADA_USERNAME, CP_OMADA_PASSWORD
# REMOVE: CP_OMADA_SITE_NAME, CP_OMADA_CONTROLLER_ID, CP_OMADA_VERIFY_SSL
# KEEP:   CP_DEBUG_GUEST_PORTAL (retained in AppSettings)
```
