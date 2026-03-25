<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Architecture Overview

## System Design

The Captive Portal Guest Access system is a Python-based web application that bridges Home Assistant Rental Control integrations with TP-Link Omada WiFi controllers to provide time-limited guest network access. It operates as either a Home Assistant add-on or standalone container.

### Design Principles

1. **Pluggable Controllers**: Abstract controller interface enables support for multiple WiFi controller types
2. **Async-First**: Non-blocking I/O for all external API calls (TP-Omada, Home Assistant)
3. **Repository Pattern**: Database abstraction layer for future storage backend migrations
4. **TDD & Contract Testing**: Comprehensive test coverage with controller API contract validation
5. **Security by Default**: Session hardening, CSRF protection, security headers, audit logging

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Captive Portal System                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐   │
│  │   Guest     │    │    Admin     │    │   Health/       │   │
│  │   Portal    │    │  Interface   │    │   Detection     │   │
│  │  (Public)   │    │   (Auth)     │    │   (Public)      │   │
│  └──────┬──────┘    └──────┬───────┘    └────────┬────────┘   │
│         │                  │                       │             │
│         └──────────────────┴───────────────────────┘             │
│                            │                                      │
│                  ┌─────────▼─────────┐                          │
│                  │   FastAPI Core    │                          │
│                  │   (Routing &      │                          │
│                  │   Middleware)     │                          │
│                  └─────────┬─────────┘                          │
│                            │                                      │
│         ┌──────────────────┼──────────────────┐                 │
│         │                  │                  │                  │
│    ┌────▼────┐      ┌─────▼──────┐    ┌─────▼──────┐          │
│    │ Voucher │      │   Grant    │    │   Audit    │          │
│    │ Service │      │  Service   │    │  Service   │          │
│    └────┬────┘      └─────┬──────┘    └─────┬──────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                 │
│                            │                                      │
│                  ┌─────────▼─────────┐                          │
│                  │  Repository Layer │                          │
│                  │    (SQLModel)     │                          │
│                  └─────────┬─────────┘                          │
│                            │                                      │
│                  ┌─────────▼─────────┐                          │
│                  │   SQLite Database │                          │
│                  └───────────────────┘                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
         │                                          │
         │ External Integrations                   │
         │                                          │
┌────────▼──────────┐                   ┌──────────▼──────────┐
│   Home Assistant  │                   │   TP-Link Omada     │
│  Rental Control   │                   │     Controller      │
│   (REST API)      │                   │    (REST API)       │
└───────────────────┘                   └─────────────────────┘
```

## Core Components

### 1. API Layer (`src/captive_portal/api/`)

**FastAPI-based HTTP interface with three primary surface areas:**

- **Guest Portal Routes** (`/guest/*`)
  - Booking code & voucher redemption
  - Self-service WiFi authorization
  - Rate-limited, CSRF-protected
  - Themeable error pages

- **Admin Interface Routes** (`/admin/*`)
  - Session-based authentication
  - Grant management (create, extend, revoke)
  - Voucher generation
  - System configuration
  - Audit log access
  - Entity mapping management
  - API documentation (`/admin/docs`, `/admin/redoc`)

- **Health & Detection Routes** (`/`, `/api/health`, `/generate_204`)
  - iOS/Android captive portal detection
  - Kubernetes liveness/readiness probes
  - No authentication required

### 2. Service Layer (`src/captive_portal/services/`)

**Business logic and orchestration:**

- **`voucher_service.py`**: Voucher creation, validation, redemption tracking
- **`grant_service.py`**: Access grant lifecycle (create, extend, revoke, cleanup)
- **`unified_code_service.py`**: Unified booking code & voucher validation
- **`audit_service.py`**: Audit log creation with unique entry IDs
- **`audit_cleanup_service.py`**: Configurable retention policy (default 30 days, max 90)
- **`cleanup_service.py`**: Expired grant cleanup (default 7 days)
- **`retry_queue_service.py`**: Reliable controller API retry with exponential backoff
- **`booking_code_validator.py`**: Case-insensitive booking code matching
- **`redirect_validator.py`**: Whitelist-based redirect URL validation
- **`cache_service.py`**: Optional TTL cache for controller status (30-60s)

### 3. Controller Abstraction (`src/captive_portal/controllers/`)

**Pluggable backend controller interface:**

- **`base.py`**: Abstract `ControllerBackend` interface defining:
  - `authorize_client(mac_address, duration_minutes)`
  - `revoke_client(mac_address)`
  - `get_client_status(mac_address)`

- **`tp_omada/`**: TP-Link Omada Controller implementation
  - External portal API integration
  - Site-aware client authorization
  - Async httpx client with retry logic
  - Contract tests with fixture validation

**Future extensibility:** UniFi, Cisco, Aruba controller adapters

### 4. Home Assistant Integration (`src/captive_portal/integrations/`)

**Rental Control synchronization:**

- **`ha_poller.py`**: 60-second polling loop
  - Fetches Rental Control entities (`sensor.rental_*`)
  - Extracts booking metadata (check-in, check-out, guest name)
  - Processes configurable attributes (`booking_code`, `checkin_code`, `access_code`)
  - Graceful backoff on HA unavailability

- **`ha_integration_config.py`** (Model): Configurable attribute mappings and grace periods

### 5. Data Models (`src/captive_portal/models/`)

**SQLModel-based domain entities:**

- **`voucher.py`**: Single-use/multi-use vouchers with expiration
- **`access_grant.py`**: Active client authorizations (MAC, expiry, booking/voucher reference)
- **`admin_user.py`**: Admin accounts with Argon2id password hashing
- **`admin_session.py`**: Session tokens with secure cookie configuration
- **`audit_log.py`**: Immutable audit records (actor, action, target_type, outcome)
- **`rental_control_event.py`**: HA booking event cache
- **`ha_integration_config.py`**: HA poller configuration
- **`portal_config.py`**: System-wide settings (theme, redirect whitelist, proxy trust)
- **`audit_config.py`**: Audit retention policy

### 6. Persistence Layer (`src/captive_portal/persistence/`)

**Repository pattern for database abstraction:**

- **`database.py`**: SQLite connection management, session lifecycle
- **`repositories.py`**: CRUD operations for all models
- **Future migration path**: PostgreSQL support via repository interface

### 7. Security Layer (`src/captive_portal/security/`)

**Authentication and session management:**

- **`session_middleware.py`**: Secure session cookie handling
  - HttpOnly, Secure (HTTPS), SameSite=strict
  - Configurable max age (default 8h)
  - Session store with expiry cleanup

- **`password_hashing.py`**: Argon2id password hashing and verification
- **CSRF Protection**: Token validation on state-changing operations

### 8. Middleware (`src/captive_portal/middleware.py`, `src/captive_portal/web/middleware/`)

**Request/response processing:**

- **`security_headers.py`**: Security header injection
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy`

- **Session Management**: Session creation, validation, expiry
- **Error Handling**: Standardized error responses with audit logging

### 9. Web Templates (`src/captive_portal/web/templates/`)

**Jinja2 templates with theming support:**

- **`guest/`**: Booking code entry, voucher redemption, success/error pages
- **`admin/`**: Login, dashboard, grant management, voucher generation
- **`portal/`**: Captive portal detection responses

**Theme System** (`src/captive_portal/web/themes/`):
- Default theme bundled
- Admin-configurable custom themes
- Precedence: admin override > default > fallback

### 10. Utilities (`src/captive_portal/utils/`)

**Cross-cutting concerns:**

- **`metrics.py`**: In-memory metrics collection (counters, gauges, histograms)
  - `active_sessions`
  - `controller_latency_seconds`
  - `auth_failures_total`
  - `voucher_redemptions_total`

- **`time_utils.py`**: UTC datetime handling
- **`network_utils.py`**: MAC address validation, client IP extraction

## Data Flow

### Guest Authorization Flow (Booking Code)

```text
1. Guest connects to WiFi → Captive portal redirect
2. GET /guest/authorize → Booking code entry form
3. POST /guest/authorize {booking_code}
   ↓
4. unified_code_service validates booking code
   ↓
5. ha_poller checks active Rental Control events
   ↓
6. Match found → grant_service creates AccessGrant
   ↓
7. Controller adapter authorizes MAC on Omada
   ↓
8. Retry queue ensures reliable propagation (25s p95)
   ↓
9. SUCCESS → Redirect to success page
   FAILURE → Error page with retry option
```

### Guest Authorization Flow (Voucher)

```text
1. Guest receives voucher code from admin/host
2. GET /guest/voucher → Voucher entry form
3. POST /guest/voucher {voucher_code}
   ↓
4. voucher_service validates code (expiry, usage limit)
   ↓
5. grant_service creates AccessGrant
   ↓
6. Controller adapter authorizes MAC on Omada
   ↓
7. voucher_service increments usage counter
   ↓
8. SUCCESS → Redirect to success page
```

### Admin Grant Management Flow

```text
1. Admin logs in → /admin/login
2. Session created (secure cookie)
3. Navigate to /admin/grants
   ↓
4. grant_service fetches active grants (paginated)
   ↓
5. Admin actions:
   - CREATE → grant_service + controller authorize
   - EXTEND → Update expiry + controller re-authorize
   - REVOKE → grant_service + controller revoke
   ↓
6. audit_service logs all operations
   ↓
7. UI updates via HTMX (no full page reload)
```

### Home Assistant Polling Flow

```text
1. ha_poller runs every 60 seconds
   ↓
2. Fetch all sensor.rental_* entities via REST API
   ↓
3. Filter active bookings (check-in ≤ now ≤ check-out + grace)
   ↓
4. Extract booking_code from configurable attributes
   ↓
5. Cache in rental_control_event repository
   ↓
6. booking_code_validator uses cache for authorization
   ↓
7. Backoff on HA unavailability (30s → 60s → 120s)
```

### Audit Log Flow

```text
1. All state-changing operations emit audit events
   ↓
2. audit_service.log(actor, action, target_type, outcome)
   ↓
3. Immutable record stored in audit_log table
   ↓
4. Admin UI displays audit trail (/admin/audit)
   ↓
5. audit_cleanup_service prunes records older than retention policy
   (default: 30 days, configurable: 1-90 days)
```

## Deployment Architecture

### Home Assistant Add-on Mode

```text
┌──────────────────────────────────────────────┐
│         Home Assistant Supervisor            │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  Captive Portal Add-on Container       │ │
│  │                                         │ │
│  │  - Port 8080 → Host network            │ │
│  │  - /data volume → Persistent storage   │ │
│  │  - /run/secrets → HA API token         │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  Home Assistant Core                   │ │
│  │  - Rental Control Integration          │ │
│  │  - REST API (http://supervisor/core)   │ │
│  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
         │
         │ Network
         │
┌────────▼──────────┐
│  TP-Link Omada    │
│  Controller       │
│  (External Portal)│
└───────────────────┘
```

**Configuration**: `/data/options.json` (managed by HA add-on config UI)

### Standalone Container Mode

```text
┌─────────────────────────────┐
│  Docker/Podman Host         │
│                             │
│  ┌───────────────────────┐ │
│  │ Captive Portal        │ │
│  │ Container             │ │
│  │                       │ │
│  │ - Port 8080:8080      │ │
│  │ - Volume: ./data      │ │
│  │ - ENV: config.yaml    │ │
│  └───────────────────────┘ │
└─────────────────────────────┘
         │
         │ Network
         │
    ┌────┴────┐
    │         │
┌───▼──┐  ┌──▼────┐
│ HA   │  │ Omada │
│(opt) │  │       │
└──────┘  └───────┘
```

**Configuration**: Environment variables or mounted `config.yaml`

## Security Architecture

### Defense Layers

1. **Transport Security**
   - HTTPS enforced for production
   - Secure cookie flags (Secure, HttpOnly)
   - HSTS header support

2. **Authentication**
   - Admin: Session-based with Argon2id passwords
   - Guest: Rate-limited, no persistent auth
   - Session expiry: 8h default (configurable)

3. **Authorization**
   - Admin endpoints: Session validation required
   - Guest endpoints: CSRF protection on POST
   - Audit log: Admin read-only access

4. **Input Validation**
   - Pydantic models for all API inputs
   - MAC address format validation
   - Booking code case-insensitive matching
   - Redirect URL whitelist

5. **Output Security**
   - Security headers on all responses
   - Content-Type enforcement
   - Frame-ancestors CSP directive

6. **Audit Trail**
   - All operations logged with:
     - User identifier
     - Action type
     - Resource affected
     - Operation result
     - Unique entry ID (UUID primary key)
   - Immutable records
   - Configurable retention (1-90 days)

## Performance Characteristics

### Target Baselines (p95)

- **Voucher redemption**: ≤800ms @ 50 concurrent / ≤900ms @ 200 concurrent
- **Admin login**: ≤300ms
- **Controller propagation**: ≤25s (authorize → client active)
- **Admin grants list**: ≤1500ms (500 grants)
- **Memory RSS**: ≤150MB
- **CPU (1-min peak)**: ≤60% @ 200 concurrent

### Optimization Strategies

1. **Async I/O**: Non-blocking httpx for all external calls
2. **Connection Pooling**: Reuse controller/HA HTTP connections
3. **Optional Caching**: TTL cache for controller status (30-60s) and HA metadata (5-10m)
4. **Database Indexing**: MAC address, expiry timestamp, booking code
5. **Retry Queue**: Offload controller operations to background workers
6. **Pagination**: Admin UI list endpoints (50 items/page default)

## Extensibility Points

### Adding New Controller Types

1. Implement `ControllerBackend` abstract interface
2. Add controller-specific configuration model
3. Provide contract tests with fixture responses
4. Register in `controllers/__init__.py`

Example:
```python
# controllers/unifi/client.py
class UniFiController(ControllerBackend):
    async def authorize_client(self, mac: str, duration: int) -> bool:
        # UniFi Network API implementation
        ...
```

### Adding New Authentication Methods

1. Extend `admin_user.py` model with new auth fields
2. Implement auth provider in `security/` module
3. Add routes in `api/routes/auth.py`
4. Update session middleware for new auth flow

### Adding New Rental Integrations

1. Create poller in `integrations/` (similar to `ha_poller.py`)
2. Implement entity mapping for booking attributes
3. Register in `booking_code_validator.py`
4. Add configuration model for integration settings

## Monitoring & Observability

### Health Endpoints

- **`GET /api/health`**: Liveness probe (returns 200 if app running)
- **`GET /api/ready`**: Readiness probe (checks DB connectivity)
- **`GET /generate_204`**: iOS/Android captive portal detection

### Metrics (Prometheus Format)

In-memory metrics tracked (Prometheus export endpoint planned for future release):

| Metric Name | Type | Description |
|---|---|---|
| `active_sessions_count` | Gauge | Current authorized clients |
| `controller_latency_seconds` | Histogram | Controller API response time |
| `auth_failures_total` | Counter | Failed authorization attempts |

**Endpoint**: In-memory metrics (export endpoint planned for future release)

### Logging

- **Python logging** with configurable log levels
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Key Events**:
  - Guest authorization attempts
  - Controller API errors
  - HA poller failures
  - Session lifecycle
  - Admin operations

**Configuration**: `LOG_LEVEL` environment variable

### Audit Trail

- **Immutable Records**: All operations logged to `audit_log` table
- **Searchable**: Admin UI provides filtering by user, action, resource, date
- **Retention**: Configurable (default 30 days)
- **Export**: JSON export for compliance reporting

## Technology Stack Summary

| Component          | Technology                    | Purpose                          |
|--------------------|-------------------------------|----------------------------------|
| **Web Framework**  | FastAPI 0.115+                | HTTP API & admin UI              |
| **Template Engine**| Jinja2 3.1+                   | HTML rendering with theming      |
| **HTTP Client**    | httpx 0.27+                   | Async controller/HA API calls    |
| **Database**       | SQLite (SQLModel 0.0.22+)     | Persistent storage               |
| **Password Hash**  | Argon2id (argon2-cffi)          | Admin credential security        |
| **Validation**     | Pydantic 2.9+                 | Input validation & serialization |
| **Testing**        | pytest + pytest-asyncio       | Unit/integration/contract tests  |
| **Linting**        | Ruff 0.8+                     | Code quality & formatting        |
| **Type Checking**  | mypy 1.13+                    | Static type validation           |
| **Package Mgmt**   | uv 0.5+                       | Fast dependency resolution       |

## References

- **Quickstart Guide**: [docs/quickstart.md](./quickstart.md)
- **HA Integration**: [docs/ha_integration_guide.md](./ha_integration_guide.md)
- **TP-Omada Setup**: [docs/tp_omada_setup.md](./tp_omada_setup.md)
- **Troubleshooting**: [docs/troubleshooting.md](./troubleshooting.md)
- **Admin UI Walkthrough**: [docs/admin_ui_walkthrough.md](./admin_ui_walkthrough.md)
- **API Documentation**: Access via `/admin/docs` after deployment
