<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Release Notes — Captive Portal MVP

**Version:** 0.1.0 (MVP)
**Status:** Draft

---

## Overview

The Captive Portal add-on provides guest network access management for
Home Assistant installations using TP-Link Omada SDN controllers. Guests
authenticate via voucher codes or Home Assistant Rental Control booking
identifiers and receive time-limited network access.

---

## Feature Summary

### Guest Portal

- Captive portal page served to unauthenticated WiFi clients (FR-001)
- Dual authentication: voucher codes **or** Rental Control booking
  identifiers (FR-002)
- Case-sensitive code validation with A-Z0-9 character set (FR-018)
- Configurable voucher length (4-24 characters, default 10)
- Clear error messages — no internal system details exposed (FR-012)
- Configurable portal theming: logo, colours, welcome message (FR-009)
- Automatic redirect after successful authentication

### TP-Link Omada SDN Integration

- Native support for Omada controller external portal API
- Create, update, and revoke client authorisations within the controller
- Exponential backoff retry logic for controller communication (FR-013)
- Retry queue for failed operations with automatic recovery
- SSL certificate verification for upstream controller connections
- Target: 95 % of admin actions propagate to controller in < 30 s
  (SC-002)

### Home Assistant Rental Control Integration

- Automatic guest access based on booking check-in / check-out times
- Configurable entity mapping to associate Rental Control entities with
  portal logic (FR-007, US3)
- 60-second polling with exponential backoff (`integrations/ha_poller.py`)
- Checkout grace period (configurable minutes)
- Mapping persists across restarts (SC-006)

### Admin Web UI

- Role-based access control with four roles: `viewer`, `auditor`,
  `operator`, `admin` (FR-017)
- Deny-by-default permission matrix with granular per-role permissions
- First-run bootstrap flow for initial admin account creation (US4)
- Additional admin account provisioning by existing administrators
- Access grant management: view, filter by status/date, extend, revoke
  (FR-004, FR-005, US2)
- Voucher creation with configurable duration and bandwidth limits
- Integration configuration UI for Rental Control entities
- Portal settings management (rate limits, redirect behaviour)

### Voucher System

- Cryptographically random voucher code generation
- Collision prevention with retry logic
  (`services/voucher_service.py`)
- Configurable duration (minutes) and optional bandwidth limits
  (up/down kbps)
- Voucher lifecycle: `unused` → `active` → `expired` / `revoked`
- Duplicate grant prevention for concurrent redemption attempts
  (FR-014)
- Target: 95 % of redemptions complete in < 60 s (SC-001)

### Audit Logging

- Comprehensive tracking of all admin actions and guest authentications
  (FR-010, SC-005)
- Immutable audit entries with UTC timestamps
- Structured fields: actor, role snapshot, action, target, outcome,
  metadata
- JSON metadata captures IP address, user-agent, and error context
- Configurable retention (1-90 days, default 30)
- Automatic cleanup of expired audit entries
- Rate limit violation tracking

### Security

- Argon2id password hashing with OWASP-recommended parameters
- CSRF protection via double-submit cookie pattern
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, Permissions-Policy
- HTTP-only secure session cookies with idle and absolute timeouts
- Per-IP rate limiting on guest authorization endpoint
- Jinja2 auto-escaping and output sanitisation
- Parameterised database queries (SQLModel / SQLAlchemy)
- Open redirect prevention via protocol allow-list

### Operational

- Operates as a Home Assistant add-on **and** standalone Docker
  container (FR-011)
- SQLite storage behind a repository abstraction layer (FR-015)
- In-memory caching and connection pooling for performance
- Async operations throughout
- Health check endpoint for monitoring
- Automatic cleanup of expired grants and vouchers (7-day retention)
- Sub-100 ms p95 latency target for voucher redemption

---

## Known Limitations

1. **Placeholder add-on packaging** — The `addon/` directory contains
   the add-on manifest but full Home Assistant add-on packaging
   (Dockerfile, build pipeline, repository publishing) is not yet
   complete.

2. **Contract tests require real hardware** — 135 contract tests for the
   TP-Link Omada controller integration are defined but require a
   physical Omada controller to execute. These tests are skipped in CI.

3. **No TLS termination** — The application serves HTTP on port 8080.
   TLS must be terminated by a reverse proxy (Home Assistant Ingress or
   an external proxy such as Nginx / Traefik).

4. **In-memory session store** — Admin sessions are stored in memory and
   are lost on restart. Admins must re-authenticate after a container or
   add-on restart.

5. **In-memory rate limiter** — Rate limit state is not persisted or
   shared across instances. A restart resets all rate limit counters.

6. **Single-instance only** — No distributed state or clustering
   support. Running multiple instances concurrently is not supported.

7. **Audit logging gaps** — Several admin account management actions
   (logout, bootstrap, account CRUD) and RBAC denials are not yet
   audited. See `docs/audit_logging_review.md` for the full gap
   analysis.

---

## Configuration Requirements

### Environment

| Requirement | Detail |
|-------------|--------|
| Python | 3.11+ |
| Database | SQLite (bundled, no external DB required) |
| Network | Access to TP-Link Omada controller API |
| HA integration | Home Assistant with Rental Control (optional) |
| TLS | Reverse proxy with TLS termination |

### Add-on Configuration (`addon/config.json`)

The add-on runs on port 8080 behind Home Assistant Ingress. Key
configuration is performed through the Admin UI after first-run
bootstrap:

- **Admin credentials** — set during bootstrap
- **Omada controller** — URL, credentials, site, SSID
- **Rental Control entities** — HA entity IDs for booking lookup
- **Portal theming** — logo, colours, welcome message
- **Rate limits** — max attempts and window duration
- **Audit retention** — 1-90 days

### First-Run Setup

1. Access the admin UI (port 8080 or via HA Ingress)
2. Complete the bootstrap form to create the initial admin account
3. Configure the Omada controller connection
4. (Optional) Configure Rental Control entity mapping
5. (Optional) Customise portal theming

---

## Breaking Changes

None — this is the initial MVP release.

---

## Upgrade Path

Not applicable for the initial release. Future releases will document
any required migration steps.
