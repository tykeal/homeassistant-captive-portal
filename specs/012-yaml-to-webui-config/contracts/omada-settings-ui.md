# Contract: Omada Settings UI

**Feature**: 012-yaml-to-webui-config
**Endpoint prefix**: `/admin/omada-settings`
**Authentication**: Admin role required (session-based)

## GET `/admin/omada-settings/`

**Purpose**: Display the Omada controller settings form.

### Request

- **Method**: GET
- **Auth**: Requires authenticated admin session (`require_admin` dependency)
- **CSRF**: Token generated and set as cookie + form hidden field

### Response: 200 OK (HTML)

Template: `admin/omada_settings.html`

**Context variables**:

| Variable | Type | Description |
|----------|------|-------------|
| `config` | `OmadaConfig` | Current Omada config (or defaults if no record) |
| `csrf_token` | `str` | CSRF token for form submission |
| `has_password` | `bool` | Whether an encrypted password is stored |
| `success_message` | `str \| None` | Success flash message from query params |
| `error_message` | `str \| None` | Error flash message from query params |
| `connection_status` | `str \| None` | "connected", "error", or None |

### Form Fields Rendered

| Field | HTML Type | Source | Notes |
|-------|-----------|--------|-------|
| `controller_url` | `<input type="url">` | `config.controller_url` | Required for connection |
| `username` | `<input type="text">` | `config.username` | Required for connection |
| `password` | `<input type="password">` | Empty (never pre-filled) | Placeholder shows "••••••••" if `has_password` |
| `password_changed` | `<input type="hidden">` | `"false"` | Set to `"true"` by JS on password input |
| `site_name` | `<input type="text">` | `config.site_name` | Defaults to "Default" |
| `controller_id` | `<input type="text">` | `config.controller_id` | Empty = auto-discover |
| `verify_ssl` | `<input type="checkbox">` | `config.verify_ssl` | Checked by default |

---

## POST `/admin/omada-settings/`

**Purpose**: Save Omada controller settings and trigger reconnection.

### Request

- **Method**: POST
- **Auth**: Requires admin role
- **Content-Type**: `application/x-www-form-urlencoded`
- **CSRF**: Validated via double-submit cookie pattern

### Form Parameters

| Parameter | Type | Required | Validation |
|-----------|------|----------|------------|
| `csrf_token` | `str` | Yes | Must match CSRF cookie |
| `controller_url` | `str` | Yes | Valid http/https URL or empty |
| `username` | `str` | Yes | Non-empty if controller_url is set |
| `password` | `str` | No | Only processed if `password_changed="true"` |
| `password_changed` | `str` | Yes | `"true"` or `"false"` |
| `site_name` | `str` | No | Defaults to "Default" if empty |
| `controller_id` | `str` | No | Hex pattern or empty (auto-discover) |
| `verify_ssl` | `str` | No | Checkbox: present="true", absent=false |

### Response: 303 Redirect

**Success**: `→ /admin/omada-settings/?success=Omada+controller+settings+saved+successfully`

**Validation Error**: `→ /admin/omada-settings/?error={error_description}`

### Server-Side Validation Rules

1. CSRF token must be valid
2. If `controller_url` is non-empty: must be valid http/https URL
3. If `controller_url` is set: `username` must be non-empty
4. If `password_changed="true"` and `controller_url` is set: `password` must be non-empty
5. If `controller_id` is non-empty: must match `^[a-fA-F0-9]{12,64}$`
6. `site_name` trimmed; defaults to "Default" if empty

### Post-Save Actions

1. Persist `OmadaConfig` to database
2. If `password_changed="true"`: encrypt new password via Fernet, store ciphertext
3. If `password_changed="false"`: preserve existing `encrypted_password`
4. Rebuild `app.state.omada_config` dict (auto-discover controller_id if empty)
5. Log audit event: `omada_config.update` (without password value)

### Audit Log Entry

```json
{
  "action": "omada_config.update",
  "target_type": "omada_config",
  "target_id": "1",
  "metadata": {
    "controller_url": "https://omada.example.com:8043",
    "username": "hotspot_operator",
    "password_changed": true,
    "site_name": "Default",
    "controller_id": "auto-discover",
    "verify_ssl": true
  }
}
```

---

## Navigation

All admin templates include the Omada settings link in the nav bar:

```html
<a href="{{ rp }}/admin/omada-settings/" class="nav-link">Omada</a>
```

Position: Between "Integrations" and "Settings" links.
