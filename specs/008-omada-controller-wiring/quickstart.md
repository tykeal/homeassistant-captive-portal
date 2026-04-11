SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Omada Controller Integration Wiring

**Feature**: 008-omada-controller-wiring
**Date**: 2025-07-11

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on branch `008-omada-controller-wiring`
- Dependencies installed: `uv sync`

## Development Setup

```bash
# Clone and setup
cd /path/to/captive-portal
git checkout 008-omada-controller-wiring
uv sync

# Run all tests
uv run pytest tests/

# Run only contract tests
uv run pytest tests/contract/tp_omada/ -v

# Run linting + type checks
uv run ruff check addon/src/ tests/
uv run mypy addon/src/
```

## Configuration (Development)

For local development without a real Omada controller, no configuration is needed. The app starts normally and skips all controller calls (graceful degradation).

To test with a controller, set environment variables:

```bash
export CP_OMADA_CONTROLLER_URL="https://192.168.1.10:8043"
export CP_OMADA_USERNAME="hotspot_operator"
export CP_OMADA_PASSWORD="your-password"
export CP_OMADA_SITE_NAME="Default"
export CP_OMADA_CONTROLLER_ID="your-controller-id"
export CP_OMADA_VERIFY_SSL="false"  # For self-signed certs
```

## Running the Applications

```bash
# Admin app (port 8080)
uv run python -m uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080

# Guest app (port 8099) — separate terminal
uv run python -m uvicorn captive_portal.guest_app:create_guest_app --factory --host 0.0.0.0 --port 8099
```

## Files Changed by This Feature

| File | Change Type | Description |
|------|-------------|-------------|
| `addon/config.yaml` | Modified | +6 Omada config schema fields |
| `addon/src/captive_portal/config/settings.py` | Modified | +6 Omada fields in AppSettings + validation |
| `addon/rootfs/.../captive-portal/run` | Modified | +export CP_OMADA_* env vars |
| `addon/rootfs/.../captive-portal-guest/run` | Modified | +export CP_OMADA_* env vars |
| `addon/src/captive_portal/app.py` | Modified | +OmadaClient/Adapter in lifespan + shutdown |
| `addon/src/captive_portal/guest_app.py` | Modified | +OmadaClient/Adapter in lifespan + shutdown |
| `addon/src/captive_portal/api/routes/guest_portal.py` | Modified | +controller authorize after grant creation |
| `addon/src/captive_portal/api/routes/grants.py` | Modified | +controller revoke after DB revocation |
| `docs/tp_omada_setup.md` | Modified | Fix port 8080→8099 in guest URLs |
| `tests/contract/tp_omada/test_authorize_flow.py` | Modified | Unskip + implement tests |
| `tests/contract/tp_omada/test_revoke_flow.py` | Modified | Unskip + implement tests |
| `tests/contract/tp_omada/test_adapter_error_retry.py` | Modified | Unskip + implement tests |

## Verification Checklist

1. **Config schema**: Add Omada fields to `addon/config.yaml` → verify HA addon config panel shows them
2. **Settings model**: Run `uv run pytest tests/unit/config/` → all settings tests pass
3. **s6 scripts**: Verify env vars exported by inspecting script output
4. **App lifespan**: Start app with/without Omada config → verify log output
5. **Authorization flow**: Submit guest code → verify grant transitions PENDING→ACTIVE
6. **Revocation flow**: Admin revoke grant → verify controller revoke call + DB update
7. **Documentation**: Review `docs/tp_omada_setup.md` → all guest URLs use port 8099
8. **Contract tests**: `uv run pytest tests/contract/tp_omada/ -v` → all pass, none skipped
9. **Full suite**: `uv run pytest tests/` → no regressions
10. **Linting**: `uv run ruff check addon/src/ tests/` → zero errors
11. **Types**: `uv run mypy addon/src/` → zero errors
