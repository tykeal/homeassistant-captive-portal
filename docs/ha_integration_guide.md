<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Home Assistant Integration Guide

This guide explains how to integrate the Captive Portal with Home Assistant Rental Control integrations for automatic guest WiFi authorization based on booking data.

## Overview

The Captive Portal can automatically synchronize booking information from Home Assistant Rental Control integrations (Airbnb, Booking.com, Guesty, etc.) to enable seamless guest WiFi access using booking codes.

### Integration Benefits

- **Automatic Booking Sync**: Guest booking data flows from Rental Control to WiFi access
- **No Manual Entry**: Guests use their booking confirmation code as WiFi access code
- **Configurable Attributes**: Choose which booking field to use (booking code, check-in code, access code)
- **Grace Periods**: Extend WiFi access before/after official check-in/check-out times
- **Centralized Management**: All booking data managed in Home Assistant

## Prerequisites

1. **Home Assistant** with Supervisor (for add-on deployment)
2. **Rental Control Integration** installed and configured
   - Examples: [Rental Control for Airbnb](https://github.com/tykeal/homeassistant-rental-control-airbnb), Booking.com, Guesty
3. **Active Bookings** with entities like `sensor.rental_<property>_<booking_id>`
4. **Long-Lived Access Token** for Home Assistant API access

## Setup Steps

### 1. Install Rental Control Integration

If not already installed:

1. Navigate to **Settings** → **Devices & Services** → **Add Integration**
2. Search for your Rental Control integration (e.g., "Rental Control Airbnb")
3. Follow the integration-specific setup wizard
4. Verify booking entities appear: **Developer Tools** → **States** → Filter `sensor.rental_`

**Expected Entity Attributes**:
```yaml
sensor.rental_property_booking123:
  state: "active"
  attributes:
    booking_code: "ABC123DEF"      # Primary booking confirmation code
    checkin_code: "456789"         # Alternative check-in code
    access_code: "WELCOME2025"     # Custom access code
    check_in: "2025-03-25T15:00:00+00:00"
    check_out: "2025-03-27T11:00:00+00:00"
    guest_name: "John Doe"
    status: "confirmed"
```

### 2. Generate Home Assistant Access Token

The Captive Portal needs API access to read booking entities:

1. Navigate to **Profile** (click your username in bottom-left)
2. Scroll to **Long-Lived Access Tokens**
3. Click **Create Token**
4. Name: `Captive Portal Integration`
5. **Copy the token** (shown only once)
6. Store securely for add-on configuration

### 3. Configure Captive Portal Add-on

Edit the add-on configuration with Home Assistant integration settings:

```yaml
# Home Assistant Integration (optional but recommended)
ha_url: http://supervisor/core  # Use supervisor URL for add-ons
ha_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # Long-lived access token

# HA Rental Control Configuration
ha_poller_enabled: true               # Enable background polling (default: true)
ha_poller_interval_seconds: 60        # Polling frequency (default: 60s)
ha_entity_pattern: "sensor.rental_*"  # Entity filter pattern (default: sensor.rental_*)

# Booking Code Attribute Selection (priority order)
ha_booking_code_attributes:
  - booking_code      # Try this attribute first
  - checkin_code      # Fallback if booking_code missing
  - access_code       # Fallback if checkin_code missing

# Grace Periods (extend WiFi access outside booking window)
ha_grace_period_before_hours: 2   # Start WiFi access 2 hours before check-in (default: 0)
ha_grace_period_after_hours: 1    # End WiFi access 1 hour after check-out (default: 0)

# Booking Code Validation
ha_booking_code_case_sensitive: false  # Case-insensitive matching (default: false)
```

**Add-on Mode Notes**:
- Use `http://supervisor/core` as `ha_url` (internal supervisor network)
- No need to expose HA API externally
- Add-on has privileged access to Home Assistant services

### 4. Configure Standalone Container (Optional)

For standalone Docker/Podman deployment, set environment variables:

```bash
docker run -d \
  --name captive-portal \
  -p 8080:8080 \
  -v ./data:/data \
  -e HA_URL=https://homeassistant.local:8123 \
  -e HA_TOKEN=your_long_lived_access_token \
  -e HA_POLLER_ENABLED=true \
  -e HA_POLLER_INTERVAL_SECONDS=60 \
  -e HA_ENTITY_PATTERN="sensor.rental_*" \
  -e HA_BOOKING_CODE_ATTRIBUTES="booking_code,checkin_code,access_code" \
  -e HA_GRACE_PERIOD_BEFORE_HOURS=2 \
  -e HA_GRACE_PERIOD_AFTER_HOURS=1 \
  ghcr.io/tykeal/homeassistant-captive-portal:latest
```

**Standalone Mode Notes**:
- Use full HA URL (e.g., `https://homeassistant.local:8123`)
- Ensure network connectivity between container and HA instance
- Consider using Docker secrets for `HA_TOKEN`

### 5. Verify Integration

After configuration:

1. **Check Add-on Logs**:
   ```
   INFO: Starting HA poller (interval=60s, max_backoff=300s)
   INFO: HA polling successful (entities_found=3, events_processed=2)
   INFO: Cached rental event: booking_code=ABC123DEF, check_in=2025-03-25, check_out=2025-03-27
   ```

2. **Test Entity Discovery**:
   - Navigate to **Admin UI** → **Integration** → **Entity Mapping**
   - Verify discovered booking entities appear in the list
   - Confirm booking codes are extracted correctly

3. **Test Guest Authorization**:
   - Connect to guest WiFi network
   - Enter booking code from active reservation
   - Verify successful WiFi authorization

## Configuration Reference

### Attribute Selection Logic

The Captive Portal checks booking entity attributes in priority order:

1. **`booking_code`** (default primary attribute)
2. **`checkin_code`** (fallback)
3. **`access_code`** (fallback)
4. **Custom attributes** (add to `ha_booking_code_attributes`)

**Example**: If a booking entity has:
```yaml
attributes:
  checkin_code: "789456"
  access_code: "WELCOME"
  # booking_code is missing
```
The Captive Portal will use `"789456"` (first available attribute).

### Grace Period Calculation

WiFi access is granted during:
```
[check_in - grace_before] to [check_out + grace_after]
```

**Example**:
- **Check-in**: 2025-03-25 15:00 UTC
- **Check-out**: 2025-03-27 11:00 UTC
- **Grace Before**: 2 hours
- **Grace After**: 1 hour
- **Effective Access**: 2025-03-25 13:00 to 2025-03-27 12:00

**Use Cases**:
- **Early Arrivals**: `grace_before` allows guests to access WiFi before official check-in
- **Late Checkouts**: `grace_after` extends WiFi during checkout process
- **Housekeeping**: Prevent access gaps between back-to-back bookings

### Entity Pattern Matching

The `ha_entity_pattern` setting uses glob-style patterns:

- **`sensor.rental_*`**: All Rental Control sensors (default)
- **`sensor.rental_property1_*`**: Single property bookings
- **`sensor.rental_*_airbnb_*`**: Airbnb bookings only
- **`sensor.rental_*`**: Match all (use with `exclude_pattern` if needed)

### Polling Behavior

**Normal Operation** (60s interval):
```
[Poll] → Fetch entities → Process events → Update cache → [Wait 60s] → [Poll]
```

**Error Handling** (exponential backoff):
```
[Poll Error] → Backoff 60s → [Poll Error] → Backoff 120s → [Poll Error] → Backoff 240s → ...
Maximum backoff: 300s (5 minutes)
```

**Recovery**: Backoff resets to normal interval on first successful poll.

## Admin UI Management

### Entity Mapping Dashboard

**Access**: Admin UI → **Integration** → **Entity Mapping**

**Features**:
- View all discovered Rental Control entities
- See extracted booking codes and time windows
- Manually refresh entity cache
- Override attribute selection per entity (advanced)
- Monitor polling status and errors

### Booking Code Validation

**Access**: Admin UI → **Grants** → **Booking Authorization**

**Features**:
- Test booking code against live HA data
- View matching entity and extracted attributes
- Check grace period applicability
- Manually authorize MAC address using booking code

### Integration Status

**Access**: Admin UI → **Settings** → **HA Integration**

**Displayed Information**:
- Poller status (running, stopped, error)
- Last successful poll timestamp
- Entities discovered count
- Active bookings count
- Error log (last 10 failures)

**Actions**:
- Enable/disable poller
- Force immediate poll
- Adjust polling interval
- Update attribute priority

## Troubleshooting

### Issue: No Entities Discovered

**Symptoms**:
- Admin UI shows 0 discovered entities
- Logs: `WARNING: No rental entities found matching pattern 'sensor.rental_*'`

**Causes & Solutions**:

1. **Rental Control Integration Not Installed**
   - Solution: Install Rental Control integration from HACS/Integration Store
   - Verify: Check **Developer Tools** → **States** for `sensor.rental_` entities

2. **Incorrect Entity Pattern**
   - Solution: Check actual entity IDs in Home Assistant
   - Update `ha_entity_pattern` to match your entities
   - Example: If entities are `sensor.bookings_*`, use that pattern

3. **No Active Bookings**
   - Solution: Verify bookings exist with check-in/check-out dates
   - Create test booking in Rental Control integration
   - Check entity `state` is `active` or similar

4. **HA API Connectivity Issues**
   - Solution: Verify `ha_url` and `ha_token` are correct
   - Check add-on logs for `Connection refused` or `Unauthorized`
   - Test token: `curl -H "Authorization: Bearer $TOKEN" $HA_URL/api/states`

### Issue: Booking Code Not Recognized

**Symptoms**:
- Guest enters booking code
- Error: "Invalid booking code"
- Logs: `DEBUG: Booking code 'ABC123' not found in cache`

**Causes & Solutions**:

1. **Attribute Name Mismatch**
   - Check entity attributes: **Developer Tools** → **States** → `sensor.rental_*`
   - Update `ha_booking_code_attributes` to match actual attribute names
   - Example: If attribute is `confirmation_code`, add it to priority list

2. **Booking Outside Grace Period**
   - Verify current time is within `[check_in - grace_before] to [check_out + grace_after]`
   - Increase grace periods if guests arrive early/leave late
   - Check entity `check_in` and `check_out` timestamps

3. **Case Sensitivity**
   - Default: Case-insensitive matching (`ABC123` == `abc123`)
   - If `ha_booking_code_case_sensitive: true`, codes must match exactly
   - Guest typos: "ABC123" vs "ABC 123" (spaces matter)

4. **Entity Not Polled Yet**
   - New bookings may take up to 60s to appear (next poll cycle)
   - Force immediate poll: Admin UI → **Integration** → **Refresh Now**
   - Check logs for last poll timestamp

### Issue: Polling Errors

**Symptoms**:
- Logs: `ERROR: HA polling error (error_count=3, backoff_seconds=240)`
- Admin UI shows "Last poll: Failed"

**Causes & Solutions**:

1. **Home Assistant Unavailable**
   - Temporary: Backoff will auto-recover when HA returns
   - Persistent: Check HA instance is running and accessible
   - Network issues: Verify connectivity between containers

2. **Invalid Access Token**
   - Error: `401 Unauthorized`
   - Solution: Generate new long-lived token
   - Update add-on configuration with new token
   - Restart add-on

3. **API Rate Limiting**
   - Error: `429 Too Many Requests`
   - Solution: Increase `ha_poller_interval_seconds` (e.g., 120)
   - Reduce concurrent API calls

4. **Malformed Entity Data**
   - Error: `ValueError: Invalid timestamp format`
   - Solution: Check entity `check_in`/`check_out` attributes are ISO-8601
   - Report issue to Rental Control integration developer

### Issue: WiFi Access Granted Outside Booking Window

**Symptoms**:
- Guest authorized after check-out time
- Admin UI shows grant beyond booking expiry

**Causes & Solutions**:

1. **Grace Period Misconfiguration**
   - Check `ha_grace_period_after_hours` setting
   - Expected: Extends access beyond check-out
   - Set to 0 for no post-checkout access

2. **Manual Grant Override**
   - Admin may have manually extended grant expiry
   - Check Audit Log: Admin UI → **Audit** → Filter by guest MAC
   - Look for "Grant Extended" actions

3. **Time Zone Mismatch**
   - HA entity times use UTC
   - Ensure system time zone configuration matches expectations
   - Check logs for timestamp parsing errors

### Issue: Duplicate Booking Codes

**Symptoms**:
- Multiple entities with same `booking_code`
- Guest authorization matches wrong booking

**Causes & Solutions**:

1. **Multiple Properties**
   - Same booking code used across properties
   - Solution: Use property-specific entity patterns
   - Example: `ha_entity_pattern: "sensor.rental_property1_*"`

2. **Historical Bookings**
   - Old booking entities not cleaned up
   - Solution: Verify entity `check_out` date
   - Only active bookings (check_out > now - grace) are cached

3. **Test Data**
   - Development bookings with placeholder codes
   - Solution: Delete test entities or use unique codes
   - Filter by entity state: Only `state: "active"` are considered

## Advanced Configuration

### Multi-Property Setups

**Scenario**: Multiple rental properties with separate controllers

**Solution 1: Entity Pattern Filtering**
```yaml
# Property 1 (Controller A)
ha_entity_pattern: "sensor.rental_property1_*"
omada_url: https://controller-a.local:8043
omada_site: Property1

# Property 2 (Controller B) - Deploy separate instance
ha_entity_pattern: "sensor.rental_property2_*"
omada_url: https://controller-b.local:8043
omada_site: Property2
```

**Solution 2: Controller Routing** (Future Enhancement)
- Entity attribute: `controller_id`
- Captive Portal routes authorization to correct controller
- Single instance, multiple controllers

### Custom Attribute Mappings

**Scenario**: Rental integration uses non-standard attribute names

**Example Entity**:
```yaml
sensor.rental_cabin_booking789:
  attributes:
    confirmation_number: "XYZ789"
    arrival_date: "2025-03-25T14:00:00Z"
    departure_date: "2025-03-27T10:00:00Z"
```

**Configuration**:
```yaml
ha_booking_code_attributes:
  - confirmation_number  # Custom attribute name

# Optional: Override date attributes (future enhancement)
ha_checkin_attribute: arrival_date
ha_checkout_attribute: departure_date
```

### Integration Disable

To run Captive Portal without Home Assistant (voucher-only mode):

```yaml
ha_poller_enabled: false  # Disable background polling
```

**Effects**:
- No automatic booking synchronization
- Guests must use admin-generated vouchers
- Entity mapping dashboard hidden
- Booking authorization endpoint disabled

### Polling Performance Tuning

**High-Volume Properties** (50+ concurrent bookings):
```yaml
ha_poller_interval_seconds: 120  # Poll less frequently (2 minutes)
ha_entity_batch_size: 100        # Process entities in batches (future)
ha_cache_ttl_seconds: 300        # Cache HA responses for 5 minutes
```

**Low-Latency Requirements** (immediate booking updates):
```yaml
ha_poller_interval_seconds: 30   # Poll every 30 seconds
ha_webhook_enabled: true         # Push updates via webhook (future)
```

## Security Considerations

### Access Token Protection

- **Never commit tokens** to version control
- Use Home Assistant Secrets: `ha_token: !secret captive_portal_token`
- Rotate tokens periodically (every 90 days recommended)
- Revoke old tokens: Profile → **Long-Lived Access Tokens** → **Revoke**

### Token Permissions

The access token requires **read-only** access to:
- `sensor.rental_*` entities (states and attributes)
- No write permissions needed
- No control of other HA entities

**Verification**:
```bash
# Test token can read entities
curl -H "Authorization: Bearer $TOKEN" \
     $HA_URL/api/states/sensor.rental_property_booking123

# Should return 200 OK with entity JSON
```

### Network Isolation

**Add-on Mode**:
- Uses internal supervisor network
- No external HA API exposure required
- Token never leaves Home Assistant host

**Standalone Mode**:
- Use internal network if possible (e.g., Docker network)
- Avoid exposing HA API to internet
- Consider VPN for remote deployments

### Audit Trail

All booking-based authorizations are logged:
```json
{
  "user": "guest",
  "action": "authorize_booking",
  "resource": "access_grant:aa:bb:cc:dd:ee:ff",
  "result": "success",
  "metadata": {
    "booking_code": "ABC123",
    "entity_id": "sensor.rental_property_booking123",
    "guest_name": "John Doe",
    "check_in": "2025-03-25T15:00:00Z",
    "check_out": "2025-03-27T11:00:00Z"
  },
  "correlation_id": "req-1234-5678",
  "timestamp": "2025-03-25T13:45:00Z"
}
```

**Access**: Admin UI → **Audit** → Filter by `authorize_booking`

## API Reference

### Entity Discovery Endpoint

**GET** `/api/integrations/ha/entities`

**Authentication**: Admin session required

**Response**:
```json
{
  "entities": [
    {
      "entity_id": "sensor.rental_property_booking123",
      "booking_code": "ABC123DEF",
      "check_in": "2025-03-25T15:00:00Z",
      "check_out": "2025-03-27T11:00:00Z",
      "guest_name": "John Doe",
      "attributes_used": "booking_code",
      "grace_period_start": "2025-03-25T13:00:00Z",
      "grace_period_end": "2025-03-27T12:00:00Z"
    }
  ],
  "total": 1,
  "last_poll": "2025-03-25T13:44:30Z"
}
```

### Booking Authorization Endpoint

**POST** `/guest/authorize`

**Authentication**: None (rate-limited)

**Request**:
```json
{
  "booking_code": "ABC123DEF",
  "mac_address": "aa:bb:cc:dd:ee:ff"
}
```

**Response** (Success):
```json
{
  "status": "authorized",
  "grant_id": "grant-uuid-1234",
  "expires_at": "2025-03-27T12:00:00Z",
  "guest_name": "John Doe"
}
```

**Response** (Error):
```json
{
  "status": "error",
  "error_code": "INVALID_BOOKING_CODE",
  "message": "Booking code not found or outside check-in window"
}
```

### Force Poll Endpoint

**POST** `/api/integrations/ha/poll`

**Authentication**: Admin session required

**Response**:
```json
{
  "status": "success",
  "entities_processed": 3,
  "events_cached": 2,
  "duration_ms": 450
}
```

## Support & Resources

- **Documentation**: [docs/troubleshooting.md](./troubleshooting.md)
- **Architecture**: [docs/architecture_overview.md](./architecture_overview.md)
- **TP-Omada Setup**: [docs/tp_omada_setup.md](./tp_omada_setup.md)
- **Issue Tracker**: [GitHub Issues](https://github.com/tykeal/homeassistant-captive-portal/issues)
- **Community Forum**: [Home Assistant Community](https://community.home-assistant.io/)

## Changelog

### v0.1.0 (2025-03)
- Initial HA integration with Rental Control support
- Configurable attribute selection and grace periods
- Case-insensitive booking code matching
- Exponential backoff on polling errors
- Entity mapping dashboard
