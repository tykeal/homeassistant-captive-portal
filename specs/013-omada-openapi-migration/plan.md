SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Implementation Plan: Omada OpenAPI Migration

**Branch**: `013-omada-openapi-migration` | **Date**: 2026-06-26 |
**Spec**: `specs/013-omada-openapi-migration/spec.md`
**Input**: Feature specification from
`/specs/013-omada-openapi-migration/spec.md`

## Summary

Migrate TP-Link Omada guest authorization from the legacy hotspot operator API
to the documented Omada OpenAPI while preserving existing guest/admin behavior
and automatic legacy fallback. The implementation will introduce a shared
`OmadaControllerAdapter` Protocol, rename/refactor the existing
`OmadaAdapter`/`OmadaClient` behavior into `OmadaLegacyAdapter`, add an
`OmadaOpenApiAdapter`, and select one backend at startup through
`openapi_mode`, credential availability, and an OpenAPI token capability probe.

OpenAPI duration handling is timer-only: the add-on's existing grant expiry
processing remains the source of truth for ending access and calls the selected
adapter's revoke/unauth operation. The OpenAPI authorize request will not depend
on any undocumented per-call controller duration parameter.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLModel, httpx, pydantic, cryptography
Fernet, uv-managed dependencies, Home Assistant add-on runtime
**Storage**: SQLite through SQLModel; singleton `OmadaConfig` row stores
controller configuration and encrypted secrets
**Testing**: pytest, ruff, mypy, interrogate, pre-commit, GitHub Actions CI
**Target Platform**: Linux Home Assistant add-on container and local FastAPI
service execution
**Project Type**: Single Python web service/add-on with admin and guest FastAPI
applications
**Performance Goals**: Preserve controller propagation within 25 seconds;
expired/admin-revoked grants initiate deauthorization within 5 seconds of
processing; avoid blocking the FastAPI event loop
**Constraints**: Existing deployments require no action; secrets never appear in
logs/audit/validation output; controller SSL verification honors existing
`verify_ssl`; backend selection is fixed until restart/reconfiguration
**Scale/Scope**: One Omada controller/site per add-on instance, current grant
volume and admin list scale from the existing application, and no guest/admin
workflow changes beyond new backend-selection configuration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality**: PASS. The plan isolates controller-specific behavior in
  adapters, keeps public async method signatures typed, requires docstrings for
  new public functions/classes, and preserves ruff/mypy/interrogate gates.
- **II. Test-Driven Development**: PASS. Implementation tasks must begin with
  failing unit/contract tests for configuration validation, factory selection,
  token handling, site discovery, MAC formatting, adapter operations, fallback,
  forced-mode errors, and expiry-driven unauth.
- **III. User Experience Consistency**: PASS. Existing guest redemption,
  redirect, admin revoke, and error semantics remain unchanged. New operator
  messages explain selected backend/fallback without exposing secrets.
- **IV. Performance Requirements**: PASS. Startup performs a bounded token probe
  only when appropriate. Token/site caches avoid per-request discovery. httpx
  calls remain async with existing timeout/retry patterns.
- **V. Atomic Commits & Compliance**: PASS. Plan artifacts are one logical docs
  change with SPDX headers. Future implementation commits must be atomic,
  signed off, and pass pre-commit without bypassing hooks.
- **VI. Phased Development**: PASS. The plan documents phased increments:
  contracts/configuration, legacy adapter extraction, OpenAPI adapter, factory
  selection, lifecycle integration, and operator documentation.

**Post-design re-check**: PASS. Research, data model, contracts, and quickstart
preserve the constitution gates. No complexity waivers are required.

## Project Structure

### Documentation (this feature)

```text
specs/013-omada-openapi-migration/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── controller-adapter.md
│   └── openapi-contracts.md
└── tasks.md             # Future /speckit.tasks output; not created now
```

### Source Code (repository root)

```text
addon/src/captive_portal/
├── api/routes/
│   ├── guest_portal.py          # authorize flow uses selected adapter
│   ├── grants.py                # admin revoke/expiry paths use selected adapter
│   └── omada_settings_ui.py     # adds OpenAPI fields/mode controls
├── config/
│   ├── omada_config.py          # builds runtime config and probes backend
│   └── settings.py              # migrates addon/env OpenAPI settings if needed
├── controllers/tp_omada/
│   ├── adapter_protocol.py      # OmadaControllerAdapter Protocol
│   ├── adapter.py               # compatibility import or legacy wrapper
│   ├── legacy_adapter.py        # existing hotspot operator behavior
│   ├── legacy_client.py         # existing session/cookie client behavior
│   ├── openapi_adapter.py       # documented OpenAPI behavior
│   ├── openapi_client.py        # token/site/auth HTTP contract helpers
│   ├── adapter_factory.py       # startup backend selection
│   └── dependencies.py          # returns selected backend per request/app state
├── models/
│   └── omada_config.py          # adds OpenAPI fields and mode
├── persistence/
│   └── database.py              # creates/migrates new columns
└── services/
    ├── config_migration.py      # preserves legacy no-action upgrades
    ├── grant_service.py         # grant lifecycle remains source of truth
    └── retry_queue_service.py   # reuses retry semantics for controller failures

tests/
├── unit/
│   ├── config/
│   ├── controllers/tp_omada/
│   └── services/
├── contract/
│   └── tp_omada/
└── integration/
```

**Structure Decision**: Keep the existing single add-on project structure. Add
new Omada modules under `controllers/tp_omada/` so protocol, legacy, OpenAPI,
and factory code remain cohesive. Route handlers depend only on the protocol and
not on backend-specific clients.

## Dual-Adapter Design

### Protocol

`OmadaControllerAdapter` is the only interface used by guest/admin flows. It
exposes async `authorize`, `revoke`, `update`, and `get_status` methods with
return dictionaries compatible with the current `OmadaAdapter`. Gateway/EAP
parameters remain accepted for legacy compatibility; OpenAPI ignores them.

### Legacy backend

`OmadaLegacyAdapter` contains the current behavior from `OmadaAdapter` and uses
the existing session/cookie client logic, renamed or wrapped as the legacy
client. It preserves legacy payloads, retries, status responses, and the
current `verify_ssl`, site name, controller ID, gateway, and EAP parameters.

### OpenAPI backend

`OmadaOpenApiAdapter` uses:

- `POST /openapi/authorize/token?grant_type=client_credentials` for the initial
  token probe/authentication.
- `POST /openapi/authorize/token?grant_type=refresh_token&refreshToken=...` for
  proactive refresh before the approximately 2-hour expiry.
- `Authorization: AccessToken=<token>` headers.
- `GET /openapi/v1/{omadacId}/sites` once to map configured `site_name` to
  `siteId`, cached for the add-on run.
- `POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{mac}/auth` for
  authorization, with MAC formatted as `AA-BB-CC-DD-EE-FF`.
- `POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{mac}/unauth` for
  admin revoke, early revoke, and grant-expiry deauthorization.
- `GET /openapi/v1/{omadacId}/sites/{siteId}/hotspot/authed-records` for
  best-effort status mapping.

### Backend factory

Startup builds an immutable backend-selection/runtime configuration and stores
that selection on app state. FastAPI dependencies then create request-scoped
adapter/client instances from that selection so legacy CSRF/cookie state is not
shared across concurrent requests. OpenAPI token and site lookup state may be
shared for the selected OpenAPI backend only through an explicit runtime cache
guarded by an `asyncio.Lock`, so token refresh and site discovery are
single-flight and concurrency-safe. The selected backend does not change
mid-run.

| `openapi_mode` | OpenAPI credentials | Probe result | Legacy credentials | Outcome |
|----------------|---------------------|--------------|--------------------|---------|
| `auto` | complete | success | any | OpenAPI |
| `auto` | complete | failure | complete | Legacy + warning |
| `auto` | missing/partial | N/A | complete | Legacy + missing-field warning when partial |
| `auto` | complete | failure | missing | Startup/config error |
| `openapi` | complete | success | any | OpenAPI |
| `openapi` | missing/partial | N/A | any | Startup/config error |
| `openapi` | complete | failure | any | Startup/config error |
| `legacy` | any | not required | complete | Legacy |
| `legacy` | any | not required | missing | Startup/config error |

Invalid mode values are rejected with supported values `auto`, `openapi`, and
`legacy`.

### Duration policy

Do not send or depend on undocumented OpenAPI duration fields. The Omada
controller hotspot portal profile must be configured with a generous maximum
duration. The add-on's grant `end_utc` remains authoritative and expiry/admin
revoke paths call the selected adapter's `revoke` operation. If implementation
finds an expiry path that only updates DB status lazily, the task phase must add
or extend the existing expiry processing point so deauthorization occurs when an
active grant expires.

## Phased Implementation Approach

1. **Contracts and config tests**: Add failing tests for `openapi_mode`,
   encrypted `client_secret`, migration/default behavior, and protocol shape.
2. **Legacy extraction**: Move existing adapter/client behavior to legacy-named
   modules while keeping compatibility imports and passing existing tests.
3. **OpenAPI client/adapter**: Implement token acquisition/refresh, site
   discovery cache, MAC conversion, auth/unauth, status mapping, retries, and
   secret-safe logging.
4. **Factory selection**: Implement startup capability probe and forced/auto
   mode behavior with operator-actionable logs/errors.
5. **Lifecycle integration**: Update FastAPI dependencies and grant/revoke/expiry
   paths to use the selected protocol backend consistently.
6. **Operator UI/docs**: Add configuration fields to the admin/settings surfaces,
   Home Assistant add-on options/migration as applicable, and quickstart docs.

## Complexity Tracking

No constitution violations or complexity waivers are required.
