SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Dual-Port Networking

**Feature**: 004-dual-port-networking
**Date**: 2025-07-15

## R-001: Dual-Listener Architecture — One App vs Two Apps

**Question**: Should both listeners share a single FastAPI app instance, or
should each listener have its own FastAPI app with selected routes?

**Decision**: Two separate FastAPI app instances (one per listener), each
constructed by its own factory function.

**Rationale**:

- **Route isolation by construction**: The guest app factory (`create_guest_app`)
  only mounts guest, captive-detection, and health routers.  Admin routes are
  never imported, never registered, and therefore unreachable — even if
  middleware or authentication is bypassed.  This satisfies FR-003 and SC-002 at
  the architectural level, not just at the authorization layer.
- **Independent middleware stacks**: The ingress app needs `SessionMiddleware`
  for admin sessions and `root_path` rewriting for ingress proxy.  The guest app
  needs neither — it needs only security headers, CSRF for guest forms, and rate
  limiting.  Separate apps avoid conditional middleware logic.
- **Independent lifecycle**: s6-overlay runs each uvicorn process independently.
  If the guest listener crashes, the ingress listener remains unaffected (FR-015,
  SC-008).  Two separate FastAPI instances make this natural.
- **Shared database**: Both apps share the same SQLite database via the same
  `create_db_engine` + `get_session` dependency.  No data duplication.

**Alternatives considered**:

| Alternative | Rejected Because |
|-------------|-----------------|
| Single app, single listener, route filtering via middleware | Admin routes would exist in the routing table and could leak through middleware bugs. Does not satisfy "unreachable by design." |
| Single app, two uvicorn workers with `--root-path` tricks | Uvicorn does not support binding multiple ports from a single process. Would require a reverse proxy (nginx, Caddy) in front — unnecessary complexity for an HA addon. |
| Reverse proxy (nginx) in front of single app | Adds a third s6 service, additional container dependency, more configuration surface. Over-engineered for the use case. |

---

## R-002: s6-overlay Multi-Service Pattern

**Question**: How should the two listeners be supervised as independent services?

**Decision**: Two `longrun` services under s6-overlay's `s6-rc.d/`:
`captive-portal` (existing, port 8080) and `captive-portal-guest` (new, port
8099).

**Rationale**:

- The existing codebase already uses s6-overlay with a `longrun` service for the
  ingress listener (see `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/`).
- The rentalsync-bridge reference project confirms the pattern: each service gets
  a directory under `s6-rc.d/` with `type` (`longrun`), `run` (executable
  script), optional `finish` (cleanup), and an entry in
  `user/contents.d/<service-name>`.
- s6-overlay (provided by HA base images) automatically manages restart,
  logging, and shutdown for each `longrun` service independently.
- No inter-service dependency is needed: both listeners can start in parallel.
  They share the SQLite database, but SQLite supports concurrent readers and
  serialized writers, which is sufficient for this workload.

**Key implementation details**:

- `captive-portal-guest/run`: Uses `#!/command/with-contenv bashio`, reads
  `guest_external_url` from addon options via bashio, exports it as
  `CP_GUEST_EXTERNAL_URL`, then `exec`s uvicorn with the guest app factory on
  port 8099.  No `--root-path` needed (guest listener is not behind ingress).
- `captive-portal-guest/finish`: Identical pattern to existing finish script —
  logs non-zero / non-256 exit codes.
- `captive-portal-guest/type`: Contains `longrun`.
- `user/contents.d/captive-portal-guest`: Empty file to register the service.
- `captive-portal-guest/dependencies.d/`: Empty directory (no dependencies).

---

## R-003: Guest Listener Port Configuration Strategy

**Question**: How should the guest port be configured, and how does it interact
with HA's native port mapping?

**Decision**: Fixed container bind port (`8099`), host-mapped port configurable
via the HA addon `ports` UI.  No separate `guest_port` schema option.

**Rationale**:

- Home Assistant addons declare container ports in `config.yaml` under `ports:`.
  The HA Supervisor maps these to host ports, and the HA UI allows
  administrators to change the host-side mapping.  This is the standard HA addon
  pattern for exposing ports (FR-005, FR-006, FR-007).
- Adding a separate `guest_port` schema option would duplicate HA's built-in
  port management, confuse administrators (two places to set the same thing),
  and violate FR-007's explicit prohibition of duplicate port configuration.
- The container always binds to `8099` internally.  The HA Supervisor maps
  `8099/tcp` to whatever host port the administrator configures (default: also
  `8099` if no override).

**config.yaml changes**:

```yaml
ports:
  "8080/tcp": null        # Ingress — not exposed on host
  "8099/tcp": 8099        # Guest portal — default host port 8099
ports_description:
  "8080/tcp": Web interface (not needed with Ingress)
  "8099/tcp": Guest captive portal (configure WiFi controller to redirect here)
```

**Alternatives considered**:

| Alternative | Rejected Because |
|-------------|-----------------|
| Expose `guest_port` as a schema option | Violates FR-007. Duplicates HA's native port mapping. Requires port-in-use validation that HA already handles. |
| Use the same port (8080) for both | Cannot serve two uvicorn processes on the same port. Would require a reverse proxy layer. |
| Dynamic port from env var | The container bind port must be fixed for Docker port mapping to work. Dynamic selection would break HA's `ports` declaration. |

---

## R-004: Port Conflict Validation

**Question**: How should the system detect and reject port conflicts between the
ingress and guest listeners?

**Decision**: Validate at startup in the guest service `run` script and in the
`AppSettings` loader.

**Rationale**:

- The container bind ports are fixed (8080 for ingress, 8099 for guest), so
  intra-container conflict is impossible by default.  However, if someone
  were to override via environment variables, validation prevents silent
  failures (FR-013).
- The `AppSettings` class already validates `db_path`; adding port conflict
  validation follows the same pattern.
- If the guest port matches the ingress port (8080), the system should refuse
  to start with a clear error message.
- Host-port conflicts are managed by HA Supervisor / Docker — the addon cannot
  detect these, and attempting to do so adds fragile host-level introspection.

---

## R-005: Guest Listener Redirect URL Strategy

**Question**: How should the guest listener generate correct external-facing
redirect URLs when the container's internal address differs from the guest's
network address?

**Decision**: New configuration field `guest_external_url` in the addon schema,
resolved via the same three-tier precedence (addon option → `CP_GUEST_EXTERNAL_URL`
env var → empty default).

**Rationale**:

- Captive detection endpoints redirect to `/guest/authorize`.  On the ingress
  listener, `root_path` (from HA ingress) provides the correct base URL.  On the
  guest listener, there is no ingress proxy — the redirect must use the external
  URL that guests can reach.
- The external URL is a static configuration (Assumption #7 in spec) set once by
  the administrator (e.g., `http://192.168.1.100:8099`).
- If `guest_external_url` is empty, the guest listener falls back to
  request-relative redirects (e.g., `/guest/authorize`) which work if the guest
  connects directly to the correct host:port.  A warning is logged (FR-009,
  User Story 5 scenario 3).

**Implementation**:

- `AppSettings` gains `guest_external_url: str = ""` with addon option key
  `guest_external_url` and env var `CP_GUEST_EXTERNAL_URL`.
- The guest app's captive detection routes use `guest_external_url` as the
  redirect base.  If empty, they use request-relative paths (graceful
  degradation).
- The ingress app's captive detection routes remain unchanged (use `root_path`).

---

## R-006: Guest App Middleware Stack

**Question**: What middleware does the guest listener need?

**Decision**: Minimal middleware stack — security headers only.  CSRF and rate
limiting are already applied as per-route FastAPI dependencies.

**Rationale**:

- **SecurityHeadersMiddleware**: Required on both listeners.  Guest listener uses
  a stricter CSP (no framing, since it's not in an HA iframe).
- **SessionMiddleware**: NOT needed on guest listener.  Guest routes do not use
  admin sessions.  The existing guest CSRF uses a separate cookie-based
  mechanism (`guest_csrftoken`).
- **CSRF**: Already implemented as a per-route dependency in `guest_portal.py`
  using `CSRFProtection` with `_guest_csrf_config`.  No middleware needed.
- **Rate limiting**: Already implemented as a per-route dependency via
  `RateLimiter` in `guest_portal.py`.  No middleware needed.

---

## R-007: Backward Compatibility Strategy

**Question**: How do we ensure existing tests and ingress behavior remain
unchanged?

**Decision**: The existing `captive-portal` s6 service and `create_app()` factory
remain **completely unchanged**.  The ingress listener continues to serve all
routes (admin + guest).  New functionality is purely additive.

**Rationale**:

- FR-004 and FR-016 require full backward compatibility.  The ingress listener
  must continue serving guest routes for debugging through the HA UI and for
  migration (Assumption #4 in spec).
- All existing tests use `create_app()` and the `TestClient`.  They never bind
  to an actual port.  They remain valid and unmodified.
- New tests for the guest listener use `create_guest_app()` with a separate
  `TestClient`.

---

## R-008: Health Endpoint Design for Dual Listeners

**Question**: Should the guest listener report the health of the ingress listener
(cross-listener health)?

**Decision**: Each listener reports its own health independently.  The guest
listener serves `/api/health`, `/api/ready`, and `/api/live` endpoints with
the same schemas but only reports its own database connectivity and liveness.

**Rationale**:

- FR-012 requires health endpoints on both listeners.  SC-008 requires
  independent operation — one listener's failure must not affect the other.
- Cross-listener health checking (e.g., guest listener probing ingress on
  port 8080) adds coupling and failure modes.  If the ingress listener is down,
  the guest listener should still report itself as healthy.
- User Story 6 scenario 3 ("reports degraded state") can be satisfied by a
  future enhancement that adds an optional `/api/health/system` endpoint.
  This is out of scope for the initial implementation.

**Implementation**: Reuse the existing `health.router` directly in the guest
app.  The `get_session` dependency works identically since both apps share the
same database engine.
