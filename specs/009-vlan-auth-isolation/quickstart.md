SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: VLAN-Based Authorization Isolation

**Feature**: 009-vlan-auth-isolation
**Date**: 2025-07-14

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on branch `009-vlan-auth-isolation`
- Dependencies installed: `uv sync --group dev`

## Development Setup

```bash
# Clone and setup
cd /path/to/captive-portal
git checkout 009-vlan-auth-isolation
uv sync --group dev

# Run all tests
uv run pytest tests/

# Run only VLAN-related tests
uv run pytest tests/unit/services/test_vlan_validation_service.py -v
uv run pytest tests/integration/test_vlan_booking_authorization.py -v
uv run pytest tests/integration/test_vlan_voucher_authorization.py -v
uv run pytest tests/integration/test_vlan_backward_compatibility.py -v

# Run linting + type checks
uv run ruff check addon/src/ tests/
uv run mypy addon/src/captive_portal
```

## Configuration (Development)

For local development, no special configuration is needed. The VLAN validation feature is opt-in per integration:

- **Without VLAN config**: All integrations and vouchers behave exactly as before (no VLAN checks)
- **With VLAN config**: Set `allowed_vlans` on integrations or vouchers via the admin API

### Example: Configure VLANs for an integration

```bash
# Create integration with VLAN restrictions
curl -X POST http://localhost:8080/api/integrations \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<admin-session-cookie>" \
  -d '{
    "integration_id": "rental_control_unit_a",
    "identifier_attr": "slot_code",
    "checkout_grace_minutes": 15,
    "allowed_vlans": [50, 51]
  }'

# Update VLAN allowlist on existing integration
curl -X PATCH http://localhost:8080/api/integrations/<config-uuid> \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<admin-session-cookie>" \
  -d '{"allowed_vlans": [50, 55]}'

# Remove VLAN restrictions (revert to unrestricted)
curl -X PATCH http://localhost:8080/api/integrations/<config-uuid> \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<admin-session-cookie>" \
  -d '{"allowed_vlans": []}'
```

### Example: Create VLAN-restricted voucher

```bash
curl -X POST http://localhost:8080/api/vouchers/ \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<admin-session-cookie>" \
  -d '{
    "duration_minutes": 1440,
    "code_length": 10,
    "allowed_vlans": [50, 51]
  }'
```

## Running the Applications

```bash
# Admin app (port 8080)
uv run python -m uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080

# Guest app (port 8099) — separate terminal
uv run python -m uvicorn captive_portal.guest_app:create_guest_app --factory --host 0.0.0.0 --port 8099
```

## Testing VLAN Validation Locally

Since the Omada controller provides the `vid` parameter in the redirect URL, you can simulate VLAN-tagged requests by including `vid` in form data when submitting to the guest authorization endpoint:

```bash
# Simulate guest authorization from VLAN 50 (should succeed if integration allows VLAN 50)
curl -X POST http://localhost:8099/guest/authorize \
  -d "code=1234&client_mac=AA:BB:CC:DD:EE:FF&vid=50&csrf_token=<token>"

# Simulate guest from VLAN 99 (should fail if integration only allows VLAN 50)
curl -X POST http://localhost:8099/guest/authorize \
  -d "code=1234&client_mac=AA:BB:CC:DD:EE:FF&vid=99&csrf_token=<token>"

# Simulate guest with no VID (should fail if integration has VLANs configured)
curl -X POST http://localhost:8099/guest/authorize \
  -d "code=1234&client_mac=AA:BB:CC:DD:EE:FF&csrf_token=<token>"
```

## Files Changed by This Feature

| File | Change Type | Description |
|------|-------------|-------------|
| `addon/src/captive_portal/models/ha_integration_config.py` | Modified | +`allowed_vlans` JSON column |
| `addon/src/captive_portal/models/voucher.py` | Modified | +`allowed_vlans` JSON column |
| `addon/src/captive_portal/services/vlan_validation_service.py` | **New** | VLAN validation logic |
| `addon/src/captive_portal/api/routes/guest_portal.py` | Modified | +VLAN validation in authorization flow |
| `addon/src/captive_portal/api/routes/integrations.py` | Modified | +`allowed_vlans` in CRUD schemas |
| `addon/src/captive_portal/api/routes/vouchers.py` | Modified | +`allowed_vlans` in create/response |
| `addon/src/captive_portal/persistence/database.py` | Modified | +2 migration functions |
| `addon/src/captive_portal/web/templates/admin/integrations.html` | Modified | +VLAN config UI section |
| `addon/src/captive_portal/web/templates/admin/vouchers.html` | Modified | +optional VLAN restriction UI |
| `tests/unit/services/test_vlan_validation_service.py` | **New** | Core validation tests |
| `tests/unit/models/test_ha_integration_config_vlans.py` | **New** | Model field validation tests |
| `tests/unit/models/test_voucher_vlans.py` | **New** | Voucher VLAN field tests |
| `tests/unit/routes/test_integrations_vlan_api.py` | **New** | Admin API VLAN tests |
| `tests/integration/test_vlan_booking_authorization.py` | **New** | Booking + VLAN e2e tests |
| `tests/integration/test_vlan_voucher_authorization.py` | **New** | Voucher + VLAN e2e tests |
| `tests/integration/test_vlan_backward_compatibility.py` | **New** | Upgrade path tests |

## Verification Checklist

1. **Migration**: Start app with existing DB → verify `allowed_vlans` columns added, no data loss
2. **Backward compat**: Authorize with no VLAN config → works exactly as before
3. **Booking + VLAN match**: Configure VLANs on integration → authorize from matching VLAN → success
4. **Booking + VLAN mismatch**: Authorize from non-matching VLAN → 403 with vague message
5. **Missing VID**: Authorize without `vid` parameter when VLANs configured → 403
6. **Voucher unrestricted**: Create voucher without VLANs → redeemable from any VLAN
7. **Voucher restricted**: Create voucher with VLANs → only matching VLANs accepted
8. **Admin API**: Create/update integration with `allowed_vlans` → persisted and returned
9. **Admin UI**: Integrations page shows VLAN configuration, accepts input
10. **Audit log**: Check audit entries include `vlan_id`, `vlan_allowed_list`, `vlan_result`
11. **Full suite**: `uv run pytest tests/` → no regressions
12. **Linting**: `uv run ruff check addon/src/ tests/` → zero errors
13. **Types**: `uv run mypy addon/src/captive_portal` → zero errors
