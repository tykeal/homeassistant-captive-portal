SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Omada OpenAPI Migration

**Feature**: 013-omada-openapi-migration
**Date**: 2026-06-26
**Status**: Complete
**Source Basis**: Pre-existing Copilot research artifact supplied during the
PLAN stage.

## Research Tasks

### R1: OpenAPI Migration Viability

**Decision**: Migrate the preferred controller backend to Omada OpenAPI for
controllers that support OpenAPI, while preserving legacy fallback.

**Rationale**: The documented Omada OpenAPI exposes hotspot client authorization
and deauthorization endpoints that map directly to the add-on's authorize and
revoke operations:
`POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{clientMac}/auth`
and `POST .../unauth`. These operations replace the legacy hotspot
`extPortal/auth` call while using a documented token-based API surface.

Sources:
https://use1-omada-northbound.tplinkcloud.com/v3/api-docs
https://github.com/Tohaker/omada-go-sdk/blob/main/omada/docs/AuthorizedClientAPI.md
https://github.com/evanjarrett/omada-open-api/blob/main/omada_open_api_client/api/authorized_client/auth_client.py
https://github.com/raulponce/portal-wifi-01/blob/main/portal-server/src/main/java/ar/com/auster/wifi/portal_server/omada/api/Client.java

**Alternatives considered**: Keep only the legacy hotspot API. Rejected because
OpenAPI is the documented controller surface and reduces reliance on session and
cookie-based hotspot operator behavior. Use network block/unblock endpoints.
Rejected because those operate at a different network layer and are not hotspot
portal authorization.

---

### R2: Duration Handling

**Decision**: Use timer-only duration handling. The add-on's grant expiry timer
or expiry-processing path remains authoritative and calls OpenAPI `unauth` (or
legacy revoke) when the add-on-managed grant expires.

**Rationale**: The official OpenAPI contract for hotspot client `auth` does not
document a request body or per-call duration parameter. Some community code
sends undocumented `duration`, `downloadLimit`, and `uploadLimit` body fields,
but this plan does not depend on them. Operators should configure the controller
hotspot portal profile with a generous maximum duration, and the add-on ends
access through explicit deauthorization at the grant expiry time.

Sources:
https://github.com/Tohaker/omada-go-sdk/blob/main/omada/docs/AuthorizedClientAPI.md
https://github.com/Rama-Mwenda/monarch-wireless/blob/main/backend/src/services/omada.js

**Alternatives considered**: Send undocumented per-call duration/body fields.
Rejected because the official generated SDKs do not document a body and the
settled product decision is timer-only. Keep OpenAPI unavailable for variable
duration grants. Rejected because explicit `unauth` provides the required
control while preserving add-on-managed expiry semantics.

---

### R3: Adapter Architecture

**Decision**: Implement a dual-adapter strategy with an
`OmadaControllerAdapter` Protocol, `OmadaLegacyAdapter`, `OmadaOpenApiAdapter`,
and a startup factory that selects one backend for the add-on run.

**Rationale**: The current `OmadaAdapter` already expresses the application
contract: authorize, revoke, update, and best-effort status by MAC. A shared
Protocol lets guest/admin flows preserve behavior while adapter implementations
translate into legacy or OpenAPI HTTP contracts. Selecting once at startup
satisfies the requirement that mid-session token failures do not switch
backends.

Sources:
https://github.com/netalertx/NetAlertX/blob/main/front/plugins/omada_sdn_openapi/script.py
https://github.com/Rama-Mwenda/monarch-wireless/blob/main/backend/src/services/omada.js

**Alternatives considered**: Inline OpenAPI conditionals in route handlers.
Rejected because it duplicates controller logic and makes fallback hard to test.
Replace the legacy adapter outright. Rejected because controllers below OpenAPI
support and existing deployments must continue working without action.

---

### R4: Authentication and Token Management

**Decision**: Use the OpenAPI `client_credentials` grant for initial
authentication and the `refresh_token` grant for proactive renewal.

**Rationale**: The daemon/add-on use case does not need an interactive operator
code flow. The token endpoint is
`POST /openapi/authorize/token?grant_type=client_credentials` with JSON
`omadacId`, `client_id`, and `client_secret`. Responses include `accessToken`,
`refreshToken`, and `expiresIn`; observed implementations and examples use an
approximately 7200-second lifetime. OpenAPI requests use
`Authorization: AccessToken=<token>`, not a standard Bearer header. Refresh at
least five minutes before expiry to avoid mid-operation expiry.

Sources:
https://github.com/netalertx/NetAlertX/blob/main/front/plugins/omada_sdn_openapi/script.py
https://github.com/speddling/lwa-infra/blob/main/services/omada/ansible/roles/omada_export/README.md
https://github.com/thefunkygibbon/InSpectre/blob/main/backend/plugins/builtin/tplink-omada.json
https://github.com/Rama-Mwenda/monarch-wireless/blob/main/backend/src/services/omada.js
https://github.com/Tohaker/omada-go-sdk/blob/main/omada/docs/AuthorizeAPI.md
https://github.com/t3knoid/omada_network/blob/main/omada/api/openapi_client.py

**Alternatives considered**: Use the `authorization_code` grant. Rejected
because it is a three-step interactive flow requiring operator username/password
and CSRF/cookie handling. Re-authenticate with client credentials for every
operation. Rejected because token caching and refresh reduce controller calls
and align with documented refresh support.

---

### R5: Capability Detection and Fallback

**Decision**: Select OpenAPI only when OpenAPI credentials are complete and a
startup token probe succeeds, unless `openapi_mode` forces another outcome.
Fallback to legacy in `auto` mode only when legacy credentials are available;
forced `openapi` mode fails clearly instead of falling back.

**Rationale**: OpenAPI support is expected on Omada SDN Controller v5.13+.
Endpoint/version probing by token request validates both controller capability
and credential correctness. The startup factory can emit a single selected
backend log and an actionable fallback warning without exposing secrets.

Sources:
https://github.com/thefunkygibbon/InSpectre/blob/main/backend/plugins/builtin/tplink-omada.json
https://github.com/netalertx/NetAlertX/blob/main/front/plugins/omada_sdn_openapi/script.py

**Alternatives considered**: Check controller version only. Rejected because
version availability in `/api/info` is not guaranteed and does not verify
OpenAPI credentials. Probe lazily at first guest authorization. Rejected because
the spec requires startup selection and clear startup/configuration errors.

---

### R6: Site and Identifier Handling

**Decision**: Continue discovering `omadacId` through `GET /api/info` when the
controller ID is not configured, and add one-time OpenAPI site discovery through
`GET /openapi/v1/{omadacId}/sites` to map configured `site_name` to `siteId`.
Cache the `siteId` for the add-on run.

**Rationale**: OpenAPI paths require both `omadacId` and opaque `siteId` path
parameters. Legacy configuration stores a human-readable site name, so OpenAPI
needs a discovery step. Caching avoids repeated site-list calls on every guest
operation.

Sources:
https://github.com/t3knoid/omada_network/blob/main/omada/api/openapi_client.py
https://github.com/Rama-Mwenda/monarch-wireless/blob/main/backend/src/services/omada.js

**Alternatives considered**: Ask operators to configure raw `siteId`. Rejected
because it adds an avoidable migration burden and existing deployments already
have `site_name`. Discover site on every operation. Rejected because the site is
stable for the add-on run and repeated discovery adds latency.

---

### R7: MAC Address Format

**Decision**: Convert MAC addresses at the OpenAPI adapter boundary to uppercase
dash-separated form, e.g. `AA-BB-CC-DD-EE-FF`.

**Rationale**: Existing guest flows and legacy payloads use colon-separated MAC
strings, while the OpenAPI hotspot client path parameter uses uppercase
dash-separated MAC values. Keeping conversion in the OpenAPI adapter preserves
route/service behavior and avoids leaking backend-specific formatting.

Sources:
https://github.com/Tohaker/omada-go-sdk/blob/main/omada/docs/AuthorizedClientAPI.md
https://github.com/Rama-Mwenda/monarch-wireless/blob/main/backend/src/services/omada.js

**Alternatives considered**: Normalize all stored MAC values to dash format.
Rejected because it risks unnecessary data migration and changes existing
external behavior. Require callers to pass dash format. Rejected because callers
should remain backend-agnostic.

---

### R8: Configuration and Secret Storage

**Decision**: Add `client_id`, encrypted `client_secret`, and `openapi_mode`
(`auto`, `openapi`, `legacy`; default `auto`) while retaining legacy
`username`/`password`. Protect `client_secret` at rest using the same Fernet
credential encryption pattern as `encrypted_password`.

**Rationale**: Existing deployments with only legacy credentials require no
action and select legacy automatically. New OpenAPI deployments create app
credentials in Omada under Settings → Platform Integration → Open API → New App.
OpenAPI secrets and tokens must receive the same log/audit secrecy guarantees as
legacy passwords.

Sources:
https://github.com/thefunkygibbon/InSpectre/blob/main/backend/plugins/builtin/tplink-omada.json

**Alternatives considered**: Replace username/password with OpenAPI credentials.
Rejected because legacy fallback and no-action upgrades are required. Store
`client_secret` in plaintext. Rejected because the existing password encryption
pattern already establishes the repository's secret-at-rest standard.

---

### R9: On-Premises and SSL Behavior

**Decision**: Use the configured controller base URL for OpenAPI calls and honor
the existing `verify_ssl` option for both backends.

**Rationale**: Community implementations confirm self-hosted controllers expose
`/openapi/...` locally, commonly on the existing HTTPS controller port such as
8043. Cloud northbound hosts are optional for cloud-managed deployments, not a
requirement for local controllers. Self-signed certificates remain common, so
OpenAPI must use the existing SSL verification toggle.

Sources:
https://github.com/speddling/lwa-infra/blob/main/services/omada/ansible/roles/omada_export/README.md
https://github.com/thefunkygibbon/InSpectre/blob/main/backend/plugins/builtin/tplink-omada.json

**Alternatives considered**: Require TP-Link cloud northbound access. Rejected
because local self-hosted controllers can expose OpenAPI without cloud
connectivity. Add a separate SSL setting for OpenAPI. Rejected because the same
controller endpoint and certificate policy apply to both backends.

## Summary

All research decisions are resolved. The implementation will use a startup
selected dual-adapter architecture, documented OpenAPI token/site/hotspot
contracts, timer-only grant duration, encrypted OpenAPI secrets, OpenAPI mode
control, and transparent legacy fallback for existing deployments.
