SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Omada Controller Integration Wiring

**Feature**: 008-omada-controller-wiring
**Date**: 2025-07-11
**Status**: Complete

## Research Tasks

### R1: Lazy Initialization Pattern for httpx.AsyncClient in FastAPI Lifespan

**Context**: The OmadaClient uses `httpx.AsyncClient` and authenticates via `__aenter__`. We need the client constructed at startup (no I/O), with authentication deferred to first use.

**Decision**: Construct `OmadaClient` at lifespan startup without entering the async context manager. The `_client` httpx instance and `_authenticate()` call happen inside `__aenter__`, so simply calling `OmadaClient(...)` performs zero network I/O — it only stores config attributes. When the first authorize/revoke call is made, the calling code must `async with client:` to open the session and authenticate. For clean shutdown, `__aexit__` closes the httpx client only if it was previously opened.

**Rationale**: The existing `OmadaClient.__init__` already follows this pattern — it stores `base_url`, `controller_id`, `username`, `password`, `verify_ssl`, `timeout` and sets `_client = None`. No network activity occurs until `__aenter__` is invoked. This means construction is synchronous and safe for lifespan startup.

**Alternative considered**: Wrapping the client in a "lazy proxy" that auto-enters the context on first call. Rejected because it adds complexity and hides lifecycle management. Explicit context entry is clearer and the adapter methods already require an active client.

**Implementation approach**: Store uninitialized `OmadaClient` and `OmadaAdapter` on `app.state`. The authorize and revoke route handlers should use `async with client:` for each operation so session creation, authentication, and cleanup follow the client's public lifecycle contract. Do not use a "session guard" based on `client._client is not None`, because that private attribute does not reliably indicate that the underlying `httpx.AsyncClient` is still open after `__aexit__`. If avoiding repeated enter/exit ever becomes necessary, that should be implemented by adding a public lifecycle indicator such as `is_open`/`is_active` or by making `__aexit__` reset `_client` to `None`, rather than depending on private state in callers.

---

### R2: Three-Tier Precedence for New Omada Settings Fields

**Context**: `AppSettings.load()` implements per-field three-tier precedence (addon JSON → env var → default). Six new Omada fields need to follow this exact pattern.

**Decision**: Extend the existing `_ADDON_OPTION_MAP`, `_ENV_VAR_MAP` dictionaries with the 6 Omada entries. Add field declarations to `AppSettings` with appropriate defaults. Add validation functions for URL and boolean types. Add the fields to the `load()` iteration list.

**Rationale**: The three-tier mechanism is already battle-tested for 7 existing fields. Following the identical pattern ensures consistency and minimizes the risk of precedence bugs.

**Field mapping**:

| Addon key | Env var | AppSettings field | Type | Default |
|-----------|---------|-------------------|------|---------|
| `omada_controller_url` | `CP_OMADA_CONTROLLER_URL` | `omada_controller_url` | `str` | `""` |
| `omada_username` | `CP_OMADA_USERNAME` | `omada_username` | `str` | `""` |
| `omada_password` | `CP_OMADA_PASSWORD` | `omada_password` | `str` | `""` |
| `omada_site_name` | `CP_OMADA_SITE_NAME` | `omada_site_name` | `str` | `"Default"` |
| `omada_controller_id` | `CP_OMADA_CONTROLLER_ID` | `omada_controller_id` | `str` | `""` |
| `omada_verify_ssl` | `CP_OMADA_VERIFY_SSL` | `omada_verify_ssl` | `bool` | `True` |

**Validation rules**:
- `omada_controller_url`: URL validation (http/https scheme, netloc present), or empty string for "not configured"
- `omada_username`, `omada_password`, `omada_controller_id`: non-empty string when present
- `omada_site_name`: non-empty string (defaults to "Default")
- `omada_verify_ssl`: boolean (true/false); env var accepts "true"/"false"/"1"/"0"

**log_effective()**: Must log `omada_password` as `"(set)"` / `"(not set)"` — never the actual value.

---

### R3: s6 Run Script Pattern for Exporting Omada Environment Variables

**Context**: The existing s6 run scripts use `bashio::config` to read addon options and export them as `CP_`-prefixed env vars. The guest script already does this for `guest_external_url`.

**Decision**: Add `bashio::config` reads for all 6 Omada options in both the admin and guest s6 run scripts. Each is read with a default of empty string and exported as a `CP_OMADA_*` env var. The `omada_verify_ssl` boolean is exported as `"true"` or `"false"` string (AppSettings will parse it).

**Rationale**: Matches the existing pattern in `captive-portal-guest/run` where `guest_external_url` is read and exported. Both processes need the Omada env vars because both apps construct their own client/adapter instances.

**Alternative considered**: Using a shared init script (`s6-rc.d/init-config/run`) that exports env vars once for all services. Rejected because s6 `with-contenv` already propagates the environment correctly and adding a shared init introduces a dependency that could delay startup.

---

### R4: FastAPI Dependency Injection for Controller Adapter

**Context**: Route handlers need access to the `OmadaAdapter` (or `None` when not configured). FastAPI's dependency injection via `Depends()` is the standard pattern.

**Decision**: Create dependency functions `get_omada_adapter()` that reads from `request.app.state.omada_adapter`. Returns `OmadaAdapter | None`. Route handlers that need controller access declare this dependency and branch on `None` for graceful degradation.

**Rationale**: This matches the existing pattern used for `ha_client` (stored on `app.state`, accessed in routes). FastAPI's DI keeps route signatures clean and enables easy mocking in tests.

**Alternative considered**: Global singleton module-level adapter. Rejected because it doesn't work with dual-app architecture (admin + guest are separate processes with independent instances).

---

### R5: Authorization Flow Integration Points

**Context**: Guest authorization creates grants with `PENDING` status. After creation, the controller needs to be called. On success → `ACTIVE`; on failure → `FAILED`.

**Decision**: After the grant is created and committed with `PENDING` status in `guest_portal.py`, add a post-creation step:
1. If `omada_adapter is not None`:
   a. Enter the client async context for this authorize operation using `async with client:`
   b. Call `adapter.authorize(mac, grant.end_utc)` within that context
   c. On success: update grant `status=ACTIVE`, store `controller_grant_id`
   d. On failure (`OmadaClientError`): update grant `status=FAILED`, log error, show user-friendly error
2. If `omada_adapter is None`: set `status=ACTIVE` directly (current behavior preserved)

**Rationale**: Keeps the controller call in the route handler where the HTTP request context (and thus the MAC address and grant) are available. The grant is committed as PENDING first so that even if the process crashes mid-controller-call, the grant state is consistent.

**Key concern**: The grant must transition atomically from PENDING to ACTIVE/FAILED. Since SQLite + SQLModel is single-writer, a simple `session.commit()` after status update is sufficient.

---

### R6: Revocation Flow Integration Points

**Context**: Admin grant revocation in `grants.py` updates the database status to `REVOKED`. The controller also needs to be notified.

**Decision**: In the revoke endpoint, after database revocation:
1. If `omada_adapter is not None` and grant has a MAC address:
   a. Attempt `adapter.revoke(mac)`
   b. On success or "already revoked": revocation complete
   c. On failure: DB grant stays REVOKED, log error, inform admin of partial failure
2. If `omada_adapter is None` or no MAC: database-only revocation (current behavior)

**Rationale**: Database revocation is never contingent on controller success (FR-016). The controller call is best-effort. This ensures the admin action always succeeds from the database perspective.

**Edge case**: Legacy grants without MAC address (FR-018) — skip controller call entirely. Check `grant.mac` before attempting revocation.

---

### R7: Contract Test Implementation Strategy

**Context**: 16 contract tests across 3 files are currently skipped. They need to be unskipped and implemented using mocks.

**Decision**: Use `unittest.mock.AsyncMock` to mock `httpx.AsyncClient` responses. Each test constructs a real `OmadaClient` and `OmadaAdapter` with mocked HTTP transport. Tests validate:
- Payload structure sent to controller
- Response parsing (grant_id, status extraction)
- Error handling (4xx vs 5xx, retry vs no-retry)
- Exponential backoff timing (mock `asyncio.sleep`)

**Rationale**: Contract tests validate the wiring between adapter and client, not the actual controller API. Mocking at the HTTP transport level tests the maximum amount of real code while staying deterministic.

**Test doubles**: Use `httpx.MockTransport` or `unittest.mock.AsyncMock` on `httpx.AsyncClient.post`. The existing test stubs already import `AsyncMock` and `httpx` — the approach is consistent with what's scaffolded.

---

### R8: Documentation Port Reference Audit

**Context**: `docs/tp_omada_setup.md` references port 8080 in guest-facing URLs. Port 8080 is admin/ingress; guests use port 8099.

**Decision**: Update 6 occurrences of port 8080 in `tp_omada_setup.md` where the context is guest-facing:
1. Line 41: External Portal URL example (`8080/guest/authorize` → `8099/guest/authorize`)
2. Line 46: Landing page example (`8080/success` → `8099/success`)
3. Line 112: Docker port mapping (keep 8080 for admin, add 8099 for guest)
4. Line 142: Full URL example with query params (`8080/guest/authorize` → `8099/guest/authorize`)
5. Line 181: Docker run port flag (`-p 8080:8080` — keep as admin; add `-p 8099:8099`)
6. Line 305: curl troubleshooting command (`8080/guest/authorize` → `8099/guest/authorize`)

**Rationale**: Port 8080 is behind HA ingress authentication — guests cannot reach it. All guest-facing URLs must use port 8099. Admin/docker references to 8080 stay where the context is administration.

---

## Summary

All 8 research areas resolved. No NEEDS CLARIFICATION items remain. All decisions align with existing codebase patterns and constitution principles.
