SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Dual-Port Networking

**Feature Branch**: `004-dual-port-networking`
**Created**: 2025-07-15
**Status**: Draft
**Input**: User description: "Dual-port networking: separate ingress admin and external guest portal listeners for the captive-portal addon"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Guest WiFi Client Reaches Captive Portal (Priority: P1)

A guest connects to the property's WiFi network. The WiFi controller (Omada) detects the unauthenticated client and redirects their browser to the captive portal's external URL. The guest sees the authorization page directly — no Home Assistant login prompt, no authentication wall. They enter their booking code or voucher, are authorized, and gain internet access.

**Why this priority**: This is the entire reason for the feature. Without a publicly accessible guest portal endpoint, the captive portal cannot function as an actual captive portal. Guests on the WiFi network do not have Home Assistant accounts and cannot authenticate through ingress.

**Independent Test**: Can be fully tested by connecting a device to the captive WiFi network, being redirected to the guest portal URL, and completing the authorization flow without encountering any HA authentication prompt.

**Acceptance Scenarios**:

1. **Given** a guest device connects to the captive WiFi network, **When** the WiFi controller redirects the device to the guest portal URL, **Then** the guest sees the authorization page without any Home Assistant login prompt.
2. **Given** a guest is on the authorization page served by the guest listener, **When** the guest submits a valid booking code, **Then** the system authorizes the guest and displays the welcome page.
3. **Given** a guest is on the authorization page served by the guest listener, **When** the guest submits a valid voucher code, **Then** the system authorizes the guest and displays the welcome page.
4. **Given** a guest device triggers a captive portal detection request (e.g., Android's `/generate_204`, Apple's `/hotspot-detect.html`), **When** the request arrives at the guest listener, **Then** the system responds with the appropriate redirect to the guest authorization page.
5. **Given** a guest is on the captive portal, **When** the guest submits an invalid or expired code, **Then** the system displays an appropriate error message on the guest error page.

---

### User Story 2 — Admin UI Continues Working via HA Sidebar (Priority: P2)

A property administrator opens Home Assistant and clicks the captive portal panel in the sidebar. The admin UI loads through the HA ingress proxy, authenticated by Home Assistant. The administrator can manage grants, vouchers, portal settings, integrations, and admin accounts exactly as before. Nothing about the admin experience changes.

**Why this priority**: The existing admin workflow must remain intact. Breaking admin access while adding guest access would be a regression. This story ensures backward compatibility.

**Independent Test**: Can be fully tested by logging into Home Assistant, navigating to the captive portal sidebar panel, and performing admin operations (viewing grants, creating vouchers, changing settings) with no change in behavior from the current system.

**Acceptance Scenarios**:

1. **Given** an administrator is logged into Home Assistant, **When** they click the captive portal sidebar panel, **Then** the admin UI loads through ingress with correct URL path rewriting.
2. **Given** the admin UI is loaded through ingress, **When** the administrator navigates admin pages (portal settings, grants, vouchers, integrations, accounts), **Then** all pages load correctly and all operations succeed.
3. **Given** the admin UI is loaded through ingress, **When** the administrator performs an action requiring session authentication, **Then** the session is validated and the action proceeds.

---

### User Story 3 — Admin Routes Isolated from Guest Port (Priority: P2)

A malicious actor or curious guest discovers the guest portal's external URL and port. They attempt to access admin routes (account management, portal configuration, audit settings) through the guest-facing port. Every such request is rejected — the admin endpoints simply do not exist on the guest listener.

**Why this priority**: Security is co-equal with backward compatibility. Exposing admin functionality on an unauthenticated public port would be a critical security vulnerability. This must be guaranteed by design, not just by authentication checks.

**Independent Test**: Can be fully tested by sending requests for all known admin routes to the guest-facing port and confirming each returns a "not found" response rather than an authentication challenge.

**Acceptance Scenarios**:

1. **Given** the guest listener is running, **When** a request is made to any `/admin/*` path on the guest port, **Then** the system returns a "not found" response (not an authentication error).
2. **Given** the guest listener is running, **When** a request is made to any `/api/admin/*` path on the guest port, **Then** the system returns a "not found" response.
3. **Given** the guest listener is running, **When** a request is made to any `/api/grants/*`, `/api/vouchers/*`, or `/api/integrations/*` path on the guest port, **Then** the system returns a "not found" response.
4. **Given** the guest listener is running, **When** a request attempts to access admin session management or account endpoints on the guest port, **Then** the system returns a "not found" response.

---

### User Story 4 — Addon Administrator Configures Guest Port (Priority: P3)

An addon administrator installs or updates the captive portal addon. In the addon configuration, they can set the guest portal's external port number. They configure the Omada controller to redirect captive portal clients to this port on the Home Assistant host's IP address. The addon starts both listeners successfully.

**Why this priority**: Configuration flexibility is important but secondary to core functionality. The port must be configurable since network environments vary, but a sensible default allows the feature to work out of the box.

**Independent Test**: Can be fully tested by changing the guest port number in the addon configuration, restarting the addon, and confirming the guest portal is reachable on the newly configured port.

**Acceptance Scenarios**:

1. **Given** the addon is installed with default configuration, **When** the addon starts, **Then** both the ingress listener (port 8080) and the guest listener (port 8099, the default guest port) start successfully.
2. **Given** the addon configuration specifies a custom guest port number, **When** the addon starts, **Then** the guest listener binds to the configured port.
3. **Given** the addon is running with a configured guest port, **When** the administrator updates the port number and restarts the addon, **Then** the guest listener starts on the new port.
4. **Given** the addon configuration, **When** the administrator views the port mapping settings, **Then** the guest port is clearly labeled and its purpose is described.

---

### User Story 5 — Guest Portal Generates Correct Redirect URLs (Priority: P3)

The Omada controller redirects unauthenticated WiFi clients to the guest portal's external URL. The guest portal needs to generate redirect URLs (e.g., after captive detection, after authorization) that use the correct external-facing host and port so the guest's browser navigates correctly. These redirects must work even though the portal runs inside a container with a different internal address.

**Why this priority**: Correct URL generation is critical for the captive portal flow to work end-to-end, but it builds on top of the basic dual-port networking being in place.

**Independent Test**: Can be fully tested by configuring the external URL in addon settings, triggering a captive detection redirect, and confirming the redirect URL uses the configured external host and port rather than the internal container address.

**Acceptance Scenarios**:

1. **Given** the guest listener is running and the external URL is configured, **When** a captive detection request arrives, **Then** the redirect uses the configured external URL as the base.
2. **Given** the guest portal generates a redirect (e.g., from captive detection to authorization page), **When** the guest's browser follows the redirect, **Then** the destination URL is reachable from the guest's network.
3. **Given** the external URL configuration is missing or empty, **When** the addon starts, **Then** the system logs a warning indicating that guest portal redirect URLs may not work correctly.

---

### User Story 6 — System Health Monitoring Across Both Ports (Priority: P4)

An operations team or monitoring system checks the health of the captive portal addon. Health, readiness, and liveness endpoints are available on the ingress listener for HA-integrated monitoring. Basic health status is also available on the guest listener to verify it is operational.

**Why this priority**: Observability is important for production operations but is an enhancement on top of the core dual-port functionality.

**Independent Test**: Can be fully tested by sending health check requests to both the ingress and guest listeners and confirming appropriate responses on each.

**Acceptance Scenarios**:

1. **Given** both listeners are running, **When** a health check request is sent to the ingress listener, **Then** the system returns health, readiness, and liveness status.
2. **Given** both listeners are running, **When** a health check request is sent to the guest listener, **Then** the system returns basic health and liveness status.
3. **Given** one listener fails to start, **When** a health check is performed on the other listener, **Then** it reports the degraded state of the overall system.

---

### Edge Cases

- What happens when the configured guest port is already in use by another service? The addon should fail to start with a clear error message indicating the port conflict.
- What happens when the guest listener crashes but the ingress listener remains healthy? The system should attempt to restart the guest listener independently and report the failure through health endpoints.
- What happens when a guest request arrives at the ingress port? It should be handled normally (ingress serves all routes including guest routes for backward compatibility during migration).
- What happens when the system starts but the external URL is not configured? The guest listener should start and serve pages, but log a warning that captive detection redirects may use incorrect URLs.
- How does the system handle a very high volume of captive detection requests during a large event? Rate limiting on the guest listener should protect against abuse while allowing legitimate detection requests through.
- What happens if the addon configuration specifies a guest port that conflicts with the ingress port (8080)? The system should reject the configuration and fail to start with a clear error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide two separate network listeners — one for admin traffic (served via Home Assistant ingress) and one for guest-facing captive portal traffic (directly accessible on the network).
- **FR-002**: The guest listener MUST serve guest authorization pages, guest API endpoints, and captive portal detection endpoints without requiring Home Assistant authentication.
- **FR-003**: The guest listener MUST NOT serve any admin routes, including admin UI pages, admin API endpoints, grant management, voucher management, integration management, or account management endpoints.
- **FR-004**: The ingress listener MUST continue to serve all current routes (admin and guest) with Home Assistant ingress authentication, preserving full backward compatibility.
- **FR-005**: The guest listener port MUST be configurable by the addon administrator through addon configuration options.
- **FR-006**: The addon MUST provide a sensible default guest port (8099) that works without explicit configuration.
- **FR-007**: The addon configuration MUST expose the guest port mapping so that Home Assistant can map it to a host port accessible on the network.
- **FR-008**: The guest listener MUST respond to captive portal detection requests from all major platforms (Android, iOS/macOS, Windows, Firefox) with appropriate redirects to the guest authorization page.
- **FR-009**: The guest portal MUST support configuration of its externally reachable URL (host and port) so that generated redirect URLs are correct from the guest's network perspective.
- **FR-010**: The guest listener MUST enforce rate limiting on authorization endpoints to prevent abuse from the public network.
- **FR-011**: The guest listener MUST enforce CSRF protection on form submissions to prevent cross-site request forgery attacks.
- **FR-012**: Both listeners MUST provide health check endpoints so that monitoring systems can verify each listener is operational.
- **FR-013**: The system MUST validate that the configured guest port does not conflict with the ingress port and reject invalid configurations with a clear error.
- **FR-014**: The system MUST start and stop both listeners as part of the addon lifecycle — both must start when the addon starts and stop when the addon stops.
- **FR-015**: If one listener fails to start or crashes, the system MUST log the failure clearly and attempt to recover independently without affecting the other listener.
- **FR-016**: All existing tests MUST continue to pass without modification (backward compatibility).
- **FR-017**: All new files MUST include SPDX license headers (`SPDX-FileCopyrightText: 2026 Andrew Grimberg`, `SPDX-License-Identifier: Apache-2.0`).

### Key Entities

- **Ingress Listener**: The network listener bound to port 8080, served behind the Home Assistant ingress proxy. Carries all admin routes and (for backward compatibility) guest routes. Authenticated through HA's auth proxy.
- **Guest Listener**: The network listener bound to a configurable port (default 8099), directly accessible on the local network. Carries only guest-facing routes (authorization, captive detection, guest API). No HA authentication required.
- **Route Policy**: The mapping that determines which routes are available on which listener. Admin routes are exclusively on the ingress listener; guest routes are on both; health endpoints are on both.
- **External URL Configuration**: The addon setting that specifies the guest portal's externally reachable address (host/IP and port), used for generating correct redirect URLs in captive portal flows.
- **Captive Detection Endpoint**: A set of well-known URLs that operating systems probe to detect captive portals. These must redirect to the guest authorization page and be available on the guest listener.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Guest WiFi clients complete the captive portal authorization flow (from WiFi connection to internet access) in under 30 seconds without encountering any Home Assistant authentication prompt.
- **SC-002**: 100% of admin route requests to the guest listener return "not found" responses — zero admin endpoints are reachable on the guest port.
- **SC-003**: All captive portal detection endpoints (Android, iOS, macOS, Windows, Firefox) respond with correct redirects within 1 second on the guest listener.
- **SC-004**: The admin UI continues to function identically through the HA sidebar panel — zero regressions in admin workflows.
- **SC-005**: All existing tests pass without modification after the dual-port feature is implemented.
- **SC-006**: Both listeners start successfully within 10 seconds of addon startup under normal conditions.
- **SC-007**: The guest listener sustains at least 50 concurrent captive detection requests without degradation (supporting a property with many simultaneous guest arrivals).
- **SC-008**: When one listener fails, the other continues operating — the system does not require both listeners to be healthy for either to function.

## Assumptions

- The Home Assistant addon framework supports exposing multiple ports in the addon's `config.yaml`, with at least one port reserved for ingress and another mapped to the host for direct network access.
- The Omada WiFi controller (or equivalent captive portal controller) can be configured with an external portal URL pointing to the guest listener's host port and IP address.
- Guest devices on the captive WiFi network have network-level access to the Home Assistant host's IP on the configured guest port (no firewall blocking between the WiFi network and the HA host).
- The ingress listener will continue to serve guest routes in addition to admin routes for backward compatibility and to support testing/debugging through the HA UI.
- The default guest port of 8099 does not conflict with commonly used ports in typical Home Assistant deployments.
- Rate limiting defaults (5 requests per 60 seconds per IP) are sufficient for legitimate guest traffic in typical property sizes (up to ~50 simultaneous guests).
- The external URL for the guest portal is a static configuration (set once by the administrator) rather than dynamically discovered, since the HA host's network address is generally stable.
- The s6-overlay service management framework used by HA addons supports running multiple long-running services with independent lifecycle management.
