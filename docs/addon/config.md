<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Home Assistant Add-on Configuration

This document describes all configuration options for the Captive Portal add-on when running in Home Assistant.

## Configuration Format

The add-on uses YAML configuration in the Home Assistant Add-on interface. Navigate to **Settings** → **Add-ons** → **Captive Portal** → **Configuration** tab.

## Required Options

### `admin_username`
**Type**: `string`
**Required**: Yes
**Default**: _(none)_

Initial administrator account username. This account has full privileges to manage the captive portal, create vouchers, configure integrations, and manage other admin users.

```yaml
admin_username: admin
```

> **Note**: After initial setup, you can create additional admin accounts via the UI and change this user's password.

### `admin_password`
**Type**: `string`
**Required**: Yes
**Default**: _(none)_
**Minimum Length**: 12 characters

Initial administrator account password. Must be at least 12 characters long.

```yaml
admin_password: "MySecurePassword123!"
```

> **Security**: Change this immediately after first login. Passwords are hashed using Argon2id before storage.

### `omada_url`
**Type**: `string` (URL)
**Required**: Yes
**Default**: _(none)_

Base URL of your TP-Link Omada controller, including protocol and port.

```yaml
omada_url: "https://192.168.1.10:8043"
```

**Examples**:
- Software controller: `https://192.168.1.10:8043`
- Hardware controller: `https://omada.local:8043`
- Cloud controller: `https://omada.mydomain.com`

> **Note**: HTTPS is strongly recommended. If using self-signed certificates, see `omada_verify_ssl` option.

### `omada_username`
**Type**: `string`
**Required**: Yes
**Default**: _(none)_

Username for Omada controller API access. Recommend creating a dedicated user for the captive portal rather than using your admin account.

```yaml
omada_username: portal_api_user
```

**Recommended Setup**:
1. Login to Omada Controller
2. Go to **Settings** → **Administrators**
3. Create new user with descriptive name (e.g., `captive_portal_api`)
4. Assign appropriate permissions (minimum: site admin for guest network management)

### `omada_password`
**Type**: `string`
**Required**: Yes
**Default**: _(none)_

Password for the Omada API user.

```yaml
omada_password: "OmadaApiPassword123"
```

> **Security**: Store in Home Assistant secrets file for production:
> ```yaml
> omada_password: !secret omada_api_password
> ```

### `omada_site`
**Type**: `string`
**Required**: Yes
**Default**: `Default`

Omada site name to manage. Most deployments use the default site.

```yaml
omada_site: Default
```

**Finding Your Site Name**:
1. Login to Omada Controller
2. Check site selector in top-right corner
3. Use exact name (case-sensitive)

## Optional Options

### Home Assistant Integration

#### `ha_url`
**Type**: `string` (URL)
**Required**: No
**Default**: `http://supervisor/core`

Home Assistant instance URL for Rental Control integration. The default works automatically for add-ons.

```yaml
ha_url: "http://supervisor/core"
```

**External HA Instance**:
```yaml
ha_url: "http://192.168.1.5:8123"
```

#### `ha_token`
**Type**: `string`
**Required**: No (auto-configured for add-ons)
**Default**: _(supervisor token)_

Long-lived access token for Home Assistant API. Not needed for add-on deployment (uses supervisor token automatically).

**For Standalone Deployment Only**:
1. Home Assistant → Profile → Long-Lived Access Tokens
2. Create token named "Captive Portal"
3. Copy token to configuration

```yaml
ha_token: "eyJ0eXAiOiJKV1QiLCJhbGc..."
```

> **Security**: Never commit tokens to version control. Use secrets:
> ```yaml
> ha_token: !secret ha_long_lived_token
> ```

### Voucher Configuration

#### `voucher_length`
**Type**: `integer`
**Required**: No
**Default**: `10`
**Range**: `4` to `24`

Default length for generated voucher codes.

```yaml
voucher_length: 12
```

**Recommendations**:
- **4-6**: Short-term events, easy verbal communication
- **8-10**: Balanced security and usability (recommended)
- **12-16**: High-security environments
- **20-24**: Maximum security (harder for users to enter)

**Character Set**: A-Z and 0-9 only (uppercase, no ambiguous characters removed for clarity).

### Security & Session Management

#### `session_lifetime_hours`
**Type**: `integer`
**Required**: No
**Default**: `24`
**Range**: `1` to `168` (1 week)

Duration admin sessions remain valid without activity.

```yaml
session_lifetime_hours: 12
```

**Recommendations**:
- **2-4 hours**: High-security environments with multiple admins
- **12-24 hours**: Standard deployments (default recommended)
- **48-168 hours**: Single admin, trusted network

> **Note**: Sessions are automatically revoked on password change or role modification.

#### `rate_limit_attempts`
**Type**: `integer`
**Required**: No
**Default**: `5`
**Range**: `1` to `1000`

Maximum guest authentication attempts per IP address per minute.

```yaml
rate_limit_attempts: 10
```

**Recommendations**:
- **3-5**: Strict security, low guest volume
- **5-10**: Balanced (default range)
- **15-30**: High guest turnover (events, conferences)
- **50+**: Testing/development only

#### `rate_limit_window_seconds`
**Type**: `integer`
**Required**: No
**Default**: `60`
**Range**: `10` to `3600`

Time window for rate limit tracking (seconds).

```yaml
rate_limit_window_seconds: 120
```

> **Example**: `rate_limit_attempts: 10` with `rate_limit_window_seconds: 60` = max 10 attempts per IP per minute.

### Guest Access Configuration

#### `checkout_grace_minutes`
**Type**: `integer`
**Required**: No
**Default**: `15`
**Range**: `0` to `30`

Grace period after booking checkout time before access is revoked.

```yaml
checkout_grace_minutes: 20
```

**Use Cases**:
- **0**: Strict checkout enforcement
- **15**: Default buffer for late departures
- **30**: Maximum flexibility for guests

#### `redirect_success_url`
**Type**: `string` (URL)
**Required**: No
**Default**: _(none - shows success message)_
**Maximum Length**: `2048` characters

URL to redirect guests after successful authentication.

```yaml
redirect_success_url: "https://welcome.example.com/guest-info"
```

**Behavior**:
- If **not set**: Display success message with "Continue" button
- If **set**: Automatic redirect after 2 seconds
- **User choice**: Guest can manually navigate elsewhere after auth

**Recommendations**:
- Portal page with Wi-Fi usage terms
- Guest information page
- Property welcome page
- _(Empty)_: Let guests navigate freely (default)

### TP-Omada Controller Options

#### `omada_verify_ssl`
**Type**: `boolean`
**Required**: No
**Default**: `true`

Verify SSL/TLS certificates when connecting to Omada controller.

```yaml
omada_verify_ssl: false
```

> **Security Warning**: Setting to `false` disables certificate verification. Only use for:
> - Testing with self-signed certificates
> - Internal networks with self-signed certs
> - **Never** for production with external exposure

**Recommended**: Keep `true` and use properly signed certificates (Let's Encrypt, commercial CA).

#### `omada_timeout_seconds`
**Type**: `integer`
**Required**: No
**Default**: `10`
**Range**: `5` to `60`

HTTP timeout for Omada API requests.

```yaml
omada_timeout_seconds: 15
```

**Recommendations**:
- **5-10**: Low-latency local network (default range)
- **15-20**: Remote controller or slow network
- **30+**: Testing/troubleshooting only

### Logging & Observability

#### `log_level`
**Type**: `string`
**Required**: No
**Default**: `INFO`
**Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

Logging verbosity level.

```yaml
log_level: DEBUG
```

**Levels**:
- **DEBUG**: Detailed diagnostics (includes request/response payloads) - **verbose**
- **INFO**: Normal operations, guest auths, admin actions - **recommended**
- **WARNING**: Potential issues, retry attempts
- **ERROR**: Failures, controller unavailability
- **CRITICAL**: System failures requiring immediate attention

> **Performance**: `DEBUG` logging can impact performance under high load. Use for troubleshooting only.

#### `audit_retention_days`
**Type**: `integer`
**Required**: No
**Default**: `30`
**Range**: `1` to `90`

Days to retain audit log entries before automatic purging.

```yaml
audit_retention_days: 60
```

**Recommendations**:
- **30**: Standard deployments (default)
- **60-90**: Extended retention for compliance needs

### Data Persistence

#### `database_path`
**Type**: `string` (file path)
**Required**: No
**Default**: `/data/captive_portal.db`

Path to SQLite database file.

```yaml
database_path: /data/captive_portal.db
```

> **Note**: Add-on `/data` directory is automatically backed up by Home Assistant. Do not change unless you have specific backup requirements.

## Example Configurations

### Minimal Configuration (Vouchers Only)

```yaml
admin_username: admin
admin_password: "SecureAdminPass123!"
omada_url: "https://192.168.1.10:8043"
omada_username: portal_api
omada_password: "OmadaPass123"
omada_site: Default
```

### With Rental Control Integration

```yaml
admin_username: admin
admin_password: "SecureAdminPass123!"
omada_url: "https://192.168.1.10:8043"
omada_username: portal_api
omada_password: "OmadaPass123"
omada_site: Default
ha_url: "http://supervisor/core"
# ha_token auto-configured for add-on
checkout_grace_minutes: 20
```

### High-Security Configuration

```yaml
admin_username: admin
admin_password: "VerySecurePassword123!@#"
omada_url: "https://omada.mydomain.com:8043"
omada_username: portal_api
omada_password: !secret omada_password
omada_site: MainSite
session_lifetime_hours: 4
rate_limit_attempts: 3
rate_limit_window_seconds: 60
voucher_length: 16
log_level: INFO
audit_retention_days: 365
```

### Development/Testing Configuration

```yaml
admin_username: testadmin
admin_password: "TestPassword123!"
omada_url: "https://192.168.1.10:8043"
omada_username: test_api
omada_password: "testpass"
omada_site: Default
omada_verify_ssl: false  # Self-signed cert
log_level: DEBUG
rate_limit_attempts: 100
session_lifetime_hours: 72
```

## Configuration Validation

The add-on validates configuration on startup. Common errors:

### Invalid `admin_password` Length
```
ERROR: admin_password must be at least 12 characters
```
**Fix**: Use longer password (minimum 12 chars).

### Invalid `voucher_length`
```
ERROR: voucher_length must be between 4 and 24
```
**Fix**: Set value in valid range.

### Omada Connection Failed
```
ERROR: Cannot connect to Omada controller at https://192.168.1.10:8043
```
**Fix**:
- Verify `omada_url` is correct
- Check network connectivity
- Verify controller is running
- Check `omada_verify_ssl` if using self-signed certs

### Invalid `omada_site`
```
ERROR: Site 'MyFacility' not found in Omada controller
```
**Fix**: Verify site name matches exactly (case-sensitive) in Omada.

## Updating Configuration

1. Navigate to **Settings** → **Add-ons** → **Captive Portal** → **Configuration**
2. Edit YAML configuration
3. Click **Save**
4. **Restart** the add-on for changes to take effect

> **Note**: Configuration changes require add-on restart. Active guest sessions are preserved, but a brief service interruption will occur.

## Environment Variable Mapping (Standalone)

For standalone deployments, add-on configuration options map to environment variables:

| Add-on Option | Environment Variable |
|---------------|---------------------|
| `admin_username` | `ADMIN_USERNAME` |
| `admin_password` | `ADMIN_PASSWORD` |
| `omada_url` | `OMADA_URL` |
| `omada_username` | `OMADA_USERNAME` |
| `omada_password` | `OMADA_PASSWORD` |
| `omada_site` | `OMADA_SITE` |
| `ha_url` | `HA_URL` |
| `ha_token` | `HA_TOKEN` |
| `voucher_length` | `VOUCHER_LENGTH` |
| `session_lifetime_hours` | `SESSION_LIFETIME_HOURS` |
| `log_level` | `LOG_LEVEL` |

## Troubleshooting

See [Troubleshooting Guide](../troubleshooting.md) for detailed diagnostics.

## Related Documentation

- [Quickstart Guide](../quickstart.md)
- [TP-Omada Setup](../tp_omada_setup.md)
- [HA Integration Guide](../ha_integration_guide.md)
- [Admin UI Walkthrough](../admin_ui_walkthrough.md)
