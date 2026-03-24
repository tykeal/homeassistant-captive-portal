<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart Guide

This guide walks you through installing and configuring the Captive Portal for guest Wi-Fi access with TP-Link Omada controllers and optional Home Assistant Rental Control integration.

## Prerequisites

- **TP-Link Omada Controller** (hardware or software) with API access enabled
- **Home Assistant** (if using Rental Control booking integration)
- **Rental Control Integration** installed in Home Assistant (optional, for booking-based guest access)

## Deployment Options

### Option 1: Home Assistant Add-on (Recommended)

1. **Add Repository**
   - Navigate to **Settings** → **Add-ons** → **Add-on Store** → **⋮** (menu) → **Repositories**
   - Add: `https://github.com/tykeal/homeassistant-captive-portal`

2. **Install Add-on**
   - Find "Captive Portal" in the add-on store
   - Click **Install**
   - Enable **Start on boot** and **Watchdog**

3. **Configure**
   Edit the add-on configuration (see [Configuration Options](#configuration-options) below):

   ```yaml
   admin_username: admin
   admin_password: your_secure_password_here
   omada_url: https://192.168.1.10:8043
   omada_username: api_user
   omada_password: api_password
   omada_site: Default
   ha_url: http://supervisor/core
   ha_token: !secret ha_long_lived_access_token
   ```

4. **Start**
   - Click **Start**
   - Check the **Log** tab for startup messages

5. **Access Admin UI**
   - Navigate to `http://<homeassistant-ip>:8080/admin`
   - Login with credentials from step 3

### Option 2: Standalone Deployment

#### Using Docker

```bash
docker run -d \
  --name captive-portal \
  -p 8080:8080 \
  -v /path/to/data:/data \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=your_secure_password \
  -e OMADA_URL=https://192.168.1.10:8043 \
  -e OMADA_USERNAME=api_user \
  -e OMADA_PASSWORD=api_password \
  -e OMADA_SITE=Default \
  ghcr.io/tykeal/captive-portal:latest  # or build locally: docker build -t captive-portal .
```

#### From Source

1. **Clone & Install**
   ```bash
   git clone https://github.com/tykeal/homeassistant-captive-portal.git
   cd homeassistant-captive-portal
   uv sync
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Run**
   ```bash
   uv run captive-portal
   ```

## Configuration Options

### Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| `admin_username` | Initial admin account username | `admin` |
| `admin_password` | Initial admin account password | `SecurePass123!` |
| `omada_url` | Omada controller base URL | `https://192.168.1.10:8043` |
| `omada_username` | Omada API user | `portal_api` |
| `omada_password` | Omada API password | `api_secret` |
| `omada_site` | Omada site name | `Default` |

### Optional Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `ha_url` | Home Assistant URL (for Rental Control) | `http://supervisor/core` (add-on) |
| `ha_token` | HA Long-Lived Access Token | _(none)_ |
| `voucher_length` | Default voucher code length | `10` |
| `session_lifetime_hours` | Admin session duration | `24` |
| `rate_limit_attempts` | Guest auth rate limit (per IP/min) | `5` |
| `log_level` | Logging verbosity | `INFO` |

> **Note:** Add-ons running on Home Assistant can use `http://supervisor/core` for HA URL with supervisor token auth automatically configured.

## Initial Setup

### 1. Configure TP-Link Omada Controller

1. **Enable External Portal**
   - Login to Omada Controller
   - Go to **Settings** → **Authentication**
   - Select your guest SSID/portal
   - Enable **External Portal Server**
   - Set Portal URL: `http://<captive-portal-ip>:8080/portal`

2. **Create API User** (Recommended)
   - Go to **Settings** → **Administrators**
   - Create dedicated user for API access
   - Assign appropriate permissions (site admin minimum)

### 2. Configure Home Assistant Integration (Optional)

If using Rental Control for booking-based guest access:

1. **Install Rental Control**
   - Add integration via HACS or manually
   - Configure your booking platform(s)

2. **Link in Captive Portal Admin UI**
   - Navigate to **Settings** → **Integrations** in the captive portal admin
   - Click **Add Integration**
   - Enter integration identifier (e.g., `airbnb_main`)
   - Select identifier attribute: `slot_code` (default) or `slot_name`
   - Save

### 3. Test Guest Access

1. **Connect device to guest Wi-Fi**
2. **Open browser** (captive portal should auto-detect)
3. **Choose auth method:**
   - **Voucher**: Enter voucher code from admin UI
   - **Booking**: Enter slot code or name from Rental Control

4. **Verify access granted** and device appears in admin dashboard

## Creating Vouchers

### Via Admin UI

1. Navigate to **Vouchers** → **Create**
2. Set **Duration** (hours or days)
3. Optionally set **Expiration date**
4. Click **Generate**
5. Copy code and provide to guest

### Via API

```bash
curl -X POST http://<ip>:8080/api/vouchers \
  -H "Cookie: session_id=<admin-session-cookie>" \
  -H "Content-Type: application/json" \
  -d '{
    "duration_minutes": 1440,
    "expires_utc": "2025-12-31T23:59:59Z"
  }'
```

## Monitoring

- **Admin Dashboard**: Real-time view of active grants, recent authentications
- **Audit Log**: Settings → Audit Log shows all admin actions
- **Health Check**: `http://<ip>:8080/api/health` - Returns controller connectivity status
- **Logs**: Add-on Log tab or `docker logs captive-portal`

## Troubleshooting

### Guest Cannot Authenticate

1. **Check Omada controller connectivity**: Admin UI → Settings → Controller Status
2. **Verify portal URL** in Omada matches deployment
3. **Review logs** for authentication errors
4. **Test voucher hasn't expired**: Admin UI → Vouchers

### Home Assistant Integration Not Working

1. **Verify HA token** has necessary permissions
2. **Check entity state** in HA Developer Tools → States
3. **Review sync status**: Admin UI → Settings → Integrations
4. **Ensure Rental Control** entities exist and are named correctly

### Controller Connection Errors

- **SSL certificate issues**: Set `omada_verify_ssl: false` in config (not recommended for production)
- **Network routing**: Ensure captive portal can reach controller IP
- **Firewall rules**: Allow outbound HTTPS from captive portal to controller

## Next Steps

- [Admin UI Walkthrough](admin_ui_walkthrough.md) - Detailed feature guide
- [Architecture Overview](architecture_overview.md) - System design and components
- [TP-Link Omada Setup](tp_omada_setup.md) - Advanced controller configuration
- [HA Integration Guide](ha_integration_guide.md) - Rental Control deep dive
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Security Best Practices

1. **Change default admin password** immediately
2. **Use HTTPS** in production (configure reverse proxy with SSL certificate)
3. **Restrict admin UI access** via firewall or VPN
4. **Rotate HA tokens** periodically
5. **Review audit logs** regularly for suspicious activity
6. **Enable rate limiting** to prevent brute-force attacks (enabled by default)

## Support

- **Documentation**: https://github.com/tykeal/homeassistant-captive-portal/docs
- **Issues**: https://github.com/tykeal/homeassistant-captive-portal/issues
- **Discussions**: https://github.com/tykeal/homeassistant-captive-portal/discussions
