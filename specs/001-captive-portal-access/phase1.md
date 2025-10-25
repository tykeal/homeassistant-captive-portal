SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Phase 1 Execution Specification – Captive Portal Guest Access

Created: 2025-10-25T15:22:31.911Z
Status: Draft (All clarifications accepted)
Feature Ref: 001-captive-portal-access (see spec.md for baseline)

## 1. Scope (Phase 1)
Deliver fully functional captive portal with TP‑Omada backend supporting voucher + booking (HA Rental Control) authentication, RBAC admin UI, audit logging, retry/backoff resilience, and persistence (SQLite). Bandwidth enforcement & multi-controller abstraction beyond TP-Omada are deferred but data model placeholders included.

## 2. Accepted Clarifications (Canonical Defaults)

1. RBAC Roles & Allowed Actions
   - viewer: read portal status, list grants (read‑only)
   - auditor: viewer + read full audit log + export (no grant mutation)
   - operator: auditor + create / extend / revoke vouchers & grants (no user/role mgmt, no system settings)
   - admin: operator + manage admins, RBAC matrix, HA entity mappings, theming, system settings
   - Deny‑by‑default; unauthorized → HTTP 403 JSON {code: RBAC_FORBIDDEN}.
2. Controller Abstraction (initial implementation: TP‑Omada)
   Methods (async): authenticate(), ensure_site(), create_grant(device_id|mac, expires_at), extend_grant(grant_id,new_expires_at), revoke_grant(grant_id), list_active(), health(). Each returns standardized Result(success|error_code, details).
3. Voucher Generation
   - Character set: A–Z 0–9 only.
   - Default length 10; configurable 4–24 bounds (admin UI). Reject out-of-bounds or invalid chars.
   - Secure RNG; collision retry up to 5 attempts then error DUPLICATE_REDEMPTION.
   - Persist length policy; reserved nullable up_kbps / down_kbps for future use.
4. API Error Codes Enum (initial)
   INVALID_INPUT, NOT_FOUND, CONFLICT, UNAUTHORIZED, RBAC_FORBIDDEN, CONTROLLER_UNAVAILABLE, CONTROLLER_TIMEOUT, RATE_LIMITED, INTERNAL_ERROR, DUPLICATE_REDEMPTION, RETRY_EXHAUSTED.
5. Booking vs Voucher Precedence
   - If valid booking (Rental Control event 0 or 1) and voucher both supplied → booking wins, voucher ignored (INFO log). Future Phase may add force_voucher override.
6. Home Assistant Rental Control Mapping
   - Per integration choose identifier attribute: slot_code (default) or slot_name; fallback to slot_name if chosen code attr empty.
   - Poll HA every 60s; stale tolerance 3 missed polls → degraded warning; after 3 more, new booking-based grants blocked (voucher flow unaffected) until freshness restored.
7. Time Handling
   - All timestamps UTC ISO 8601; booking identifiers case-sensitive end-to-end.
   - Access grant lifetime & expiry resolution: minute precision; creation rounds down, extensions round up (ceil) to next minute.
8. Audit Retention
   - Phase 1: indefinite retention (no purge). Future phase: configurable purge policy.
9. Retry / Backoff Strategy
   - Controller operations: exponential 1s,2s,4s,8s (max 4 attempts) → then mark CONTROLLER_UNAVAILABLE.
   - Unique constraint (voucher collision) retries: 50ms,100ms,200ms (max 3) → then RETRY_EXHAUSTED.
10. Session Management & Revocation
    - Admin auth via secure HTTP-only server-side session cookie (SameSite=Lax, Secure when HTTPS).
    - Idle timeout 24h; rotate on privilege escalation; immediate revocation on password or role change (invalidate server session state).
11. Bandwidth Fields (Forward Compatibility)
    - Schema includes nullable up_kbps/down_kbps with CHECK > 0 when set; not enforced in Phase 1; API ignores if provided (logs notice).
12. Device Identification
    - Primary: client MAC captured at portal auth; fallback temporary session token if MAC unavailable (e.g., proxy) which must be reconciled to MAC within 30s or grant revoked and user re‑auth required.

## 3. Data Model (Additions / Phase 1 Constraints)
- Voucher(code PK, length_policy_id FK?, created_utc, duration_minutes, expires_utc (derived), up_kbps NULL, down_kbps NULL, status ENUM, booking_ref NULLABLE, redeemed_count, last_redeemed_utc NULL).
- AccessGrant(id PK, voucher_code FK NULLABLE, booking_ref NULLABLE, mac, session_token NULLABLE, start_utc, end_utc, controller_grant_id, status ENUM(active|revoked|expired|pending), created_utc, updated_utc).
- AdminUser(id PK, username UNIQUE, role ENUM, password_hash, created_utc, last_login_utc, active BOOL, version INT for optimistic lock).
- AuditLog(id PK, actor, role_snapshot, action, target_type, target_id, timestamp_utc, outcome, meta JSON).
- HAIntegrationConfig(id PK, integration_id, identifier_attr ENUM(slot_code|slot_name), last_sync_utc, stale_count INT).

## 4. Critical Invariants
- Single active AccessGrant per (mac, booking_ref OR voucher_code) tuple at a time.
- Voucher cannot be redeemed after its computed expiration (created + duration) even if controller grant still active (system must revoke).
- Controller operations are idempotent at service layer: repeating create after timeout checks internal state before external call.

## 5. Out of Scope (Explicit Deferrals)
- Multi-controller (beyond TP‑Omada).
- Bandwidth throttling enforcement.
- Force voucher precedence flag.
- Automatic purge / archival of audit logs.
- Guest self-service extension / upsell flows.
- Multi-tenancy beyond single logical site.

## 6. Security Considerations
- CSRF tokens on all POST/PUT/PATCH/DELETE admin endpoints.
- Rate limit guest submission endpoint (default: 10 attempts / 60s / IP) returning RATE_LIMITED on breach.
- Hash vouchers at rest (optional Phase 1 enhancement?) – DECISION: store plaintext (A-Z0-9 only) Phase 1 for support simplicity; add hashing Phase 2.
- Input validation centralized; reject any client-supplied timestamps.

## 7. Observability
- Structured JSON logs level INFO+; correlation_id per request (header or generated).
- Health endpoint exposes controller connectivity state & HA sync freshness.
- Metrics (pending exporter): grant_create_latency_ms, controller_retry_count, voucher_collision_count.

## 8. Minimal Test Matrix (Phase 1)
| Area | Key Tests |
|------|-----------|
| Voucher Generation | Length bounds, invalid chars, collision retry exhaustion |
| Booking Precedence | Voucher+booking → booking chosen, log present |
| RBAC | Each role denied disallowed actions; admin full access |
| Controller Failure | create_grant with simulated timeouts triggers backoff sequence |
| Time Rounding | Creation vs extension minute rounding behavior |
| HA Staleness | Missed polls increments stale_count & blocks new booking grants after threshold |
| Session Revocation | Role change invalidates prior session cookie |
| Duplicate Redemption | 100 concurrent requests → 1 grant |

## 9. Implementation Order (Suggested)
1. Persistence schema & models (Voucher, AccessGrant, AdminUser, AuditLog, HAIntegrationConfig).
2. RBAC middleware + session auth.
3. Voucher generation & redemption service (without controller calls).
4. Controller abstraction + TP-Omada adapter (create/revoke/extend/list).
5. Access grant orchestration (booking precedence + retries).
6. HA Rental Control polling + mapping config UI.
7. Admin UI pages (grants list, voucher CRUD, mapping, audit log, settings).
8. Captive portal guest UI & flow integration.
9. Observability (health endpoint, logging enrichment, metrics placeholders).
10. Hardening (rate limiting, CSRF, tests for edge cases).

## 10. Acceptance Gate (Phase 1 Complete When)
- All success criteria SC-001 .. SC-006 met in test environment.
- RBAC matrix enforced & audited.
- No open P1/P2 defects related to clarifications list.
- Pre-commit & CI pipeline green on main feature branch.

---
(End of Phase 1 Draft Specification)
