<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# TP-Link Omada Controller Setup Guide

This guide explains how to configure your TP-Link Omada Controller (hardware or software) to work with the Captive Portal system for guest WiFi access management.

## Overview

The Captive Portal integrates with TP-Link Omada Controllers using the **External Portal API** to authorize and revoke guest devices on your WiFi network. This guide covers controller prerequisites, external portal configuration, and API access setup.

### Prerequisites

- **Omada Controller** version 5.0.15 or higher
  - Hardware Controller: OC200, OC300
  - Software Controller: Windows/Linux installation
  - Cloud-based Controller (Omada Cloud) - see Cloud Mode section
- **Network Access**: Captive Portal must reach controller on HTTPS (default port 8043)
- **Admin Credentials**: Controller administrator account for initial setup
- **Site Configuration**: At least one site created (default: "Default")

## Controller Configuration Steps

### Step 1: Enable External Portal

1. **Log in to Omada Controller**
   - Access controller web interface (e.g., `https://192.168.1.10:8043`)
   - Enter administrator credentials

2. **Navigate to Portal Settings**
   - Go to **Settings** → **Authentication** → **Portal**
   - Or: **Wireless Networks** → Select SSID → **Portal** tab

3. **Create External Portal Profile**
   - Click **Create New Portal**
   - **Portal Type**: Select **External Portal**
   - **Portal Name**: `Captive Portal Guest Access` (or your preference)
   - **External Portal URL**: Enter Captive Portal address
     - Example: `https://captiveportal.local:8080/guest/authorize`
     - Must be reachable from clients (use public IP or hostname if needed)

4. **Configure Portal Parameters**
   - **Landing Page**: URL to redirect after successful auth
     - Example: `https://www.example.com` or `http://captiveportal.local:8080/success`
   - **Authentication Timeout**: 5 minutes (default)
   - **Terms of Service**: Enable if required (optional)

5. **Save Portal Profile**

### Step 2: Create Guest SSID

1. **Navigate to Wireless Settings**
   - Go to **Settings** → **Wireless Networks** → **SSIDs**

2. **Create New SSID** (or edit existing guest network)
   - **SSID Name**: `Guest WiFi` (or your preference)
   - **Network**: Create new guest network or use existing
   - **Security**:
     - **Open** (no password) - recommended for captive portal
     - Or **WPA2-PSK** with simple password shared with guests

3. **Enable Portal Authentication**
   - Scroll to **Portal** section
   - **Portal**: Enable
   - **Portal Profile**: Select the External Portal profile created in Step 1
   - **Portal Customization**: Configure branding (optional)

4. **Configure Access Control**
   - **VLAN**: Assign guest VLAN (isolate from main network)
   - **Client Isolation**: Enable (prevents guest-to-guest communication)
   - **Rate Limiting**: Set bandwidth limits if desired

5. **Apply Settings**
   - Click **Apply** (controller will provision settings to APs)
   - Wait 30-60 seconds for propagation

### Step 3: Create Hotspot Manager Account

The Captive Portal requires an **operator account** to authenticate API calls.

1. **Navigate to Hotspot Manager**
   - Go to **Settings** → **Authentication** → **Hotspot Manager**

2. **Create Operator Account**
   - Click **Create New Operator**
   - **Username**: `captive_portal_api` (or your preference)
   - **Password**: Generate strong password (16+ characters)
     - Example: `kD8#nQ2@mP5!xR7$`
   - **Privileges**:
     - **Authorize Clients**: ✓ (required)
     - **View Client Status**: ✓ (recommended)
     - **Manage Vouchers**: ✗ (not needed)
   - **Description**: `Captive Portal API Access`

3. **Save Credentials**
   - Copy username and password for Captive Portal configuration
   - Store securely (needed for `omada_username` and `omada_password`)

4. **Test Account**
   - Click **Test Connection** (if available)
   - Or proceed to Captive Portal configuration

### Step 4: Configure Firewall Rules (Optional)

If using VLANs or strict firewall policies:

1. **Allow Guest VLAN to Captive Portal**
   - Source: Guest VLAN (e.g., `192.168.20.0/24`)
   - Destination: Captive Portal IP/hostname
   - Ports: `8080/tcp` (HTTP) and/or `8443/tcp` (HTTPS)
   - Action: **Allow**

2. **Allow Captive Portal to Controller**
   - Source: Captive Portal server IP
   - Destination: Controller IP
   - Port: `8043/tcp` (HTTPS)
   - Action: **Allow**

3. **Block Guest-to-LAN (Recommended)**
   - Source: Guest VLAN
   - Destination: Internal LAN subnets
   - Action: **Deny**
   - Exception: Captive Portal server

4. **Allow Guest Internet Access**
   - Source: Guest VLAN
   - Destination: Internet (any)
   - Action: **Allow** (after portal authentication)

### Step 5: Verify External Portal Integration

1. **Check Portal Detection**
   - Connect device to guest SSID
   - Open browser → Should redirect to Omada Controller
   - Controller redirects to Captive Portal URL

2. **Verify Portal Parameters**
   - Captive Portal should receive URL like:
     ```
     https://captiveportal.local:8080/guest/authorize?clientMac=AA:BB:CC:DD:EE:FF&apMac=00:11:22:33:44:55&ssidName=Guest+WiFi&t=1711234567890123&radioId=1&site=Default&redirectUrl=https://www.example.com
     ```
   - Check Captive Portal logs for incoming requests

3. **Test Authorization Flow**
   - Enter test booking code or voucher
   - Captive Portal calls controller API to authorize MAC
   - Device should gain internet access within 25 seconds (p95 target)
   - Verify redirect to landing page

## Captive Portal Configuration

After completing controller setup, configure the Captive Portal with connection details:

### Home Assistant Add-on Configuration

Edit add-on config in **Settings** → **Add-ons** → **Captive Portal** → **Configuration**:

```yaml
# TP-Omada Controller Settings
omada_url: https://192.168.1.10:8043  # Controller HTTPS URL
omada_username: captive_portal_api    # Hotspot operator username (Step 3)
omada_password: kD8#nQ2@mP5!xR7$      # Hotspot operator password
omada_site: Default                   # Site name (case-sensitive, usually "Default")

# Connection Settings (optional)
omada_verify_ssl: true                # Set false for self-signed certs (not recommended)
omada_timeout_seconds: 30             # API request timeout
omada_retry_attempts: 3               # Retry failed API calls
omada_retry_backoff_seconds: 5        # Exponential backoff base
```

### Standalone Container Configuration

Set environment variables:

```bash
docker run -d \
  --name captive-portal \
  -p 8080:8080 \
  -v ./data:/data \
  -e OMADA_URL=https://192.168.1.10:8043 \
  -e OMADA_USERNAME=captive_portal_api \
  -e OMADA_PASSWORD=kD8#nQ2@mP5!xR7$ \
  -e OMADA_SITE=Default \
  -e OMADA_VERIFY_SSL=true \
  ghcr.io/tykeal/homeassistant-captive-portal:latest
```

## Advanced Configuration

### Multi-Site Deployments

If you manage multiple properties/sites in one Omada Controller:

**Option 1: Separate Captive Portal Instances**
```yaml
# Property 1 Instance
omada_site: Property1
omada_url: https://controller.local:8043

# Property 2 Instance (separate container)
omada_site: Property2
omada_url: https://controller.local:8043
```

**Option 2: Site Routing** (Future Feature)
- Configure site mapping in Captive Portal
- Route authorizations based on SSID or VLAN
- Single Captive Portal instance, multiple sites

### Custom Bandwidth Limits

Configure per-grant bandwidth shaping:

```yaml
# Default bandwidth limits (kbps)
omada_default_upload_kbps: 10240    # 10 Mbps upload
omada_default_download_kbps: 51200  # 50 Mbps download

# Premium grants (admin UI override)
# Set per-grant in Admin → Grants → Create/Edit
```

Controller applies limits to authorized clients.

### Cloud-Based Controllers (Omada Cloud)

**Requirements**:
- Omada Cloud subscription
- Public API endpoint (provided by TP-Link)
- API key authentication (instead of username/password)

**Configuration** (Future Support):
```yaml
omada_cloud_enabled: true
omada_cloud_api_key: your_cloud_api_key
omada_cloud_region: us-east  # Or: eu-west, ap-southeast
```

**Current Workaround**:
- Use local controller access (if available)
- Or deploy software controller on-premises

### SSL Certificate Handling

**Production (Recommended)**:
- Use valid SSL certificates on controller
- Set `omada_verify_ssl: true`

**Development/Testing**:
- Self-signed certificates: Set `omada_verify_ssl: false`
- **Security Risk**: Susceptible to MITM attacks
- Use only in isolated test environments

**Best Practice**:
- Install custom CA certificate in Captive Portal container
- Keep SSL verification enabled

### High Availability

**Active-Passive Setup**:
1. Primary Omada Controller at `192.168.1.10`
2. Standby Controller at `192.168.1.11`
3. Captive Portal monitors primary, fails over to standby

**Configuration** (Future Feature):
```yaml
omada_urls:
  - https://192.168.1.10:8043  # Primary
  - https://192.168.1.11:8043  # Standby
omada_failover_timeout_seconds: 30
```

**Current Workaround**:
- Use load balancer VIP in front of controllers
- Or manually update configuration on failover

## Troubleshooting

### Issue: Client Not Redirected to Portal

**Symptoms**:
- Guest connects to WiFi
- No captive portal redirect
- Cannot access internet

**Causes & Solutions**:

1. **Portal Not Enabled on SSID**
   - Verify: **Wireless Networks** → SSID → **Portal** = Enabled
   - Ensure External Portal profile is selected

2. **Client Already Authorized**
   - Previous authorization still active
   - Wait for expiry or manually revoke: **Insights** → **Active Clients** → Unauthorize

3. **DNS/DHCP Issues**
   - Verify guest VLAN has DHCP server
   - Check DNS servers are reachable (controller provides DNS redirect)

4. **Firewall Blocking Portal**
   - Verify guest VLAN can reach Captive Portal URL
   - Check: `curl https://captiveportal.local:8080/guest/authorize` from guest network

5. **iOS/Android Detection Failure**
   - Implement captive portal detection endpoints:
     - `GET /generate_204` (Android)
     - `GET /hotspot-detect.html` (iOS)
   - Return HTTP 200 when authenticated, 302 redirect when not

### Issue: API Authentication Failed

**Symptoms**:
- Captive Portal logs: `401 Unauthorized` or `403 Forbidden`
- Guest authorization fails after portal submission

**Causes & Solutions**:

1. **Incorrect Operator Credentials**
   - Verify `omada_username` and `omada_password` match Hotspot Manager account
   - Test login: `curl -X POST https://$CONTROLLER:8043/$CONTROLLER_ID/api/v2/hotspot/login -d '{"name":"$USER","password":"$PASS"}'`

2. **Insufficient Operator Privileges**
   - Check Hotspot Manager account has **Authorize Clients** permission
   - Re-create operator with correct privileges

3. **CSRF Token Missing**
   - Ensure API calls include `Csrf-Token` header
   - Captive Portal handles this automatically (verify implementation)

4. **Controller ID Mismatch**
   - URL requires controller ID: `/[controller-id]/api/v2/hotspot/login`
   - Captive Portal auto-discovers controller ID on first request

5. **Session Expired**
   - Operator sessions expire after 30 minutes
   - Captive Portal automatically re-authenticates

### Issue: Authorization Delay

**Symptoms**:
- Guest receives "success" message
- Internet access takes 30-60 seconds to activate
- Controller propagation exceeds 25s target

**Causes & Solutions**:

1. **Network Latency**
   - High RTT between Captive Portal and controller
   - Solution: Ensure Captive Portal and controller on same network segment

2. **AP Synchronization Delay**
   - Controller → AP propagation time
   - Solution: Reduce AP polling interval (if supported)
   - Wait time: Usually 10-20 seconds

3. **Retry Queue Backlog**
   - API retries accumulating
   - Check Captive Portal metrics: `omada_controller_latency_seconds`
   - Solution: Increase `omada_timeout_seconds` or retry limits

4. **Controller Overload**
   - High client count or CPU usage
   - Check controller **System** → **Controller Status**
   - Solution: Upgrade controller hardware or reduce client load

### Issue: SSL Certificate Errors

**Symptoms**:
- Captive Portal logs: `SSL: CERTIFICATE_VERIFY_FAILED`
- Cannot connect to controller API

**Causes & Solutions**:

1. **Self-Signed Certificate**
   - Quick Fix: Set `omada_verify_ssl: false` (development only)
   - Production Fix: Install custom CA in container

2. **Certificate Expired**
   - Check controller certificate validity
   - Renew certificate via controller admin interface

3. **Hostname Mismatch**
   - Certificate issued for `omada.local` but using IP `192.168.1.10`
   - Solution: Use hostname in `omada_url` that matches certificate CN/SAN

4. **Intermediate CA Missing**
   - Install full certificate chain on controller
   - Include root and intermediate CAs

### Issue: Client Revocation Not Working

**Symptoms**:
- Admin revokes grant in Captive Portal UI
- Guest device still has internet access

**Causes & Solutions**:

1. **Controller Cache**
   - Authorization cached on AP/Gateway
   - Wait 60 seconds for cache expiry
   - Or force client disconnect via controller UI

2. **API Call Failed**
   - Check Captive Portal audit log for revoke errors
   - Verify operator account has revoke privileges

3. **Wrong MAC Address**
   - Verify MAC address format (colon-separated: `AA:BB:CC:DD:EE:FF`)
   - Some devices randomize MAC (iOS Private Relay) - cannot track

4. **Multiple Active Grants**
   - Device authorized under different MAC (WiFi vs Ethernet)
   - Check all grants for guest and revoke all

## Monitoring & Validation

### Health Checks

Captive Portal provides controller connectivity health endpoints:

- **`GET /api/ready`**: Readiness probe
  - Returns 200 if database is accessible
  - Returns 503 if database unavailable
  - Use for Kubernetes readiness checks

- **`GET /api/health`**: Liveness probe
  - Returns 200 if app running
  - Does not check external dependencies

### Metrics

Monitor controller integration via application logs and health endpoints:

```prometheus
# Controller API latency
captive_portal_controller_latency_seconds{operation="authorize"} 0.450
captive_portal_controller_latency_seconds{operation="revoke"} 0.320

# API call failures
captive_portal_controller_errors_total{operation="authorize"} 3
captive_portal_controller_errors_total{operation="revoke"} 0

# Active authorizations
captive_portal_active_sessions{site="Default"} 12
```

### Controller Logs

Access Omada Controller logs for debugging:

1. **Log Location**:
   - Hardware Controller: **Logs** → **Controller Logs**
   - Software Controller: `/opt/tplink/OmadaController/logs/`

2. **Relevant Events**:
   - External portal redirects
   - Client authorization/deauthorization
   - API authentication attempts

3. **Log Levels**:
   - Increase verbosity: **Settings** → **Services** → **Log Level** = DEBUG

### Audit Trail

Captive Portal logs all controller operations:

- **Admin UI** → **Audit** → Filter by `controller_authorize` or `controller_revoke`
- Includes correlation IDs for cross-referencing with controller logs

## API Reference

### Authorize Client Endpoint

**POST** `https://{controller}:8043/{controller-id}/api/v2/hotspot/extPortalAuth`

**Headers**:
```
Content-Type: application/json
Csrf-Token: {token_from_login_response}
```

**Request**:
```json
{
  "clientMac": "AA:BB:CC:DD:EE:FF",
  "site": "Default",
  "time": 1711234567890123,  // Expiry timestamp (microseconds)
  "authType": 4,              // External portal auth
  "upKbps": 10240,            // Upload limit (0 = unlimited)
  "downKbps": 51200           // Download limit (0 = unlimited)
}
```

**Response** (Success):
```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "clientId": "AA:BB:CC:DD:EE:FF",
    "authorized": true
  }
}
```

### Revoke Client Endpoint

**POST** `https://{controller}:8043/{controller-id}/api/v2/hotspot/unauthorize`

**Request**:
```json
{
  "clientMac": "AA:BB:CC:DD:EE:FF",
  "site": "Default"
}
```

### Get Client Status Endpoint

**GET** `https://{controller}:8043/{controller-id}/api/v2/sites/{site}/clients/{mac}`

**Response**:
```json
{
  "result": {
    "mac": "AA:BB:CC:DD:EE:FF",
    "ip": "192.168.20.100",
    "authorized": true,
    "ssid": "Guest WiFi",
    "uptime": 3600,
    "tx": 1048576,  // Bytes uploaded
    "rx": 5242880   // Bytes downloaded
  }
}
```

## Security Best Practices

1. **Use Strong Operator Password**
   - 16+ characters, mixed case, numbers, symbols
   - Rotate every 90 days

2. **Enable SSL Certificate Verification**
   - Always use `omada_verify_ssl: true` in production
   - Deploy valid certificates on controller

3. **Isolate Guest VLAN**
   - Separate VLAN for guest WiFi
   - Firewall rules blocking guest-to-LAN traffic

4. **Limit Operator Privileges**
   - Hotspot operator account: authorize/revoke only
   - No admin or configuration access

5. **Monitor API Access**
   - Review Captive Portal audit logs regularly
   - Alert on authentication failures

6. **Network Segmentation**
   - Place Captive Portal in DMZ or management VLAN
   - Restrict controller management interface access

## Support & Resources

- **Captive Portal Docs**: [docs/troubleshooting.md](./troubleshooting.md)
- **Architecture**: [docs/architecture_overview.md](./architecture_overview.md)
- **HA Integration**: [docs/ha_integration_guide.md](./ha_integration_guide.md)
- **TP-Link Omada API**: [FAQ 3231](https://www.tp-link.com/support/faq/3231/)
- **Controller Manual**: [Omada SDN Controller User Guide](https://www.tp-link.com/support/download/omada-software-controller/)

## Changelog

### v0.1.0 (2025-03)
- Initial TP-Omada Controller integration
- External Portal API support (v5.0.15+)
- Authorize/revoke/status operations
- Retry queue with exponential backoff
- SSL certificate verification
