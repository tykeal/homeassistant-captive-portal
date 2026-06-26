SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Omada OpenAPI Migration

**Feature**: 013-omada-openapi-migration
**Date**: 2026-06-26

## Existing Deployments

No operator action is required after upgrade. If `client_id` and
`client_secret` are not configured, the add-on selects the legacy Omada backend
when the existing controller URL, username, password, site name, and SSL
settings are available. The controller ID remains optional when the existing
discovery behavior can resolve it.

## Enable OpenAPI

1. Upgrade the Omada controller to a version that exposes OpenAPI. The planned
   minimum supported OpenAPI controller version is v5.13+.
2. In the Omada controller UI, create an OpenAPI application:
   **Settings → Platform Integration → Open API → New App**.
3. Copy the generated Client ID and Client Secret.
4. In the add-on Omada settings, set:

   ```text
   client_id=<Omada OpenAPI Client ID>
   client_secret=<Omada OpenAPI Client Secret>
   openapi_mode=auto
   ```

5. Keep existing legacy username/password configured if you want automatic
   fallback in `auto` mode when the OpenAPI probe fails.
6. Restart or save/reload Omada settings so the startup capability probe runs.

## Backend Modes

| Mode | Behavior |
|------|----------|
| `auto` | Default. Use OpenAPI only when credentials are complete and token probe succeeds; otherwise use legacy when legacy credentials are configured. |
| `openapi` | Force OpenAPI. Missing credentials or failed probe is a startup/configuration error. No legacy fallback occurs. |
| `legacy` | Force legacy. OpenAPI credentials may be present but are ignored and no OpenAPI probe is required. |

Invalid values are rejected. Supported values are exactly `auto`, `openapi`, and
`legacy`.

## Duration Guidance

OpenAPI authorization does not rely on an undocumented per-call duration
parameter. Configure the Omada hotspot portal profile with a maximum duration
that exceeds the longest expected add-on-managed grant. The add-on remains the
source of truth for guest access duration and calls the selected backend's
revoke/unauth operation when a grant expires or an admin revokes it.

## Expected Logs

Startup logs should identify the selected backend and a secret-safe reason, for
example:

```text
Omada backend selected: openapi (OpenAPI token probe succeeded)
Omada backend selected: legacy (OpenAPI credentials not configured)
OpenAPI probe failed; falling back to legacy backend
```

Logs must never include legacy passwords, OpenAPI client secrets, access tokens,
or refresh tokens.

## Developer Verification

```bash
uv run pytest tests/unit/config/ tests/unit/controllers/tp_omada/ tests/contract/tp_omada/
uv run ruff check addon/src/ tests/
uv run mypy addon/src/captive_portal
```

Targeted tests should cover:

1. `openapi_mode` validation and defaulting to `auto`.
2. `client_secret` encryption/decryption and log redaction.
3. Factory selection for `auto`, `openapi`, and `legacy`.
4. Token acquisition, refresh, and `AccessToken=` authorization header.
5. Site discovery and cache behavior.
6. MAC conversion to uppercase dash format.
7. OpenAPI `auth`, `unauth`, and `authed-records` contract mapping.
8. Legacy fallback preserving existing authorize/revoke/status behavior.
9. Expiry/admin revoke calling the selected backend's deauthorization method.
