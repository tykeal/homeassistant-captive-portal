<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Phase 3 Decisions

**Date**: 2025-10-26T14:54:00Z
**Phase**: Phase 3 - Controller Integration (HA + TP-Omada)
**Status**: ✅ APPROVED

---

## Decision D5: HA Integration Library

**Decision**: Use direct REST API calls to Home Assistant

**Rationale**:
- Lightweight (no full HA library dependency)
- Runs as Home Assistant addon (has local network access)
- Can use Supervisor API for local HA communication
- Simplifies testing (mock HTTP responses)
- 60s polling doesn't need WebSocket complexity

**Implementation**:
- HTTP client: `httpx` (async support)
- Endpoint: `http://supervisor/core/api/states/<entity_id>`
- Authentication: Supervisor token (automatic for addons)
- Response: JSON entity state with attributes

**File**: `src/captive_portal/integrations/ha_client.py`

**Approved**: 2025-10-26T14:54:00Z

---

## Decision D6: HA Polling Strategy

**Decision**: Poll all configured integrations, synchronized batch, exponential backoff on errors

**Strategy Details**:

**1. Integration Selection**: Poll ALL configured integrations
- Query: `SELECT * FROM ha_integration_config WHERE enabled=true`
- For each integration, poll calendar + event sensors
- Admin disables unwanted integrations via config table

**2. Polling Timing**: Synchronized batch every 60 seconds
- All integrations polled at same time
- Simpler than staggered (acceptable overhead)
- Background task runs every 60s via asyncio

**3. Error Handling**: Exponential backoff on HA unavailable
- Normal: 60s interval
- Error 1: Wait 60s, retry
- Error 2: Wait 120s, retry
- Error 3: Wait 240s, retry
- Error 4+: Wait 300s (max), retry
- Success: Resume 60s interval
- Log all errors to AuditService

**Implementation**:
- Background task: `asyncio.create_task()` with `asyncio.sleep(60)`
- Error counter: In-memory (reset on success)
- Backoff schedule: `min(60 * (2 ** error_count), 300)`

**File**: `src/captive_portal/integrations/ha_poller.py`

**Approved**: 2025-10-26T14:54:00Z

---

## Decision D7: Booking Identifier Attribute Selection

**Decision**: Per-integration configuration, default `slot_code`, include `last_four` option

**Configuration**:

**Database Schema Addition**:
```python
# HAIntegrationConfig model addition
auth_attribute: str = Field(default="slot_code")  # "slot_code" | "slot_name" | "last_four"
```

**Attribute Options**:
1. **`slot_code`** (DEFAULT): Numeric string `^\d{4,}$` (4+ digits, more secure)
2. **`slot_name`**: Freeform string (guest name, less secure)
3. **`last_four`**: Numeric string `^\d{4}$` (exactly 4 digits, least secure)

**Fallback Logic**: If selected attribute is empty/missing, try in order:
1. Configured `auth_attribute`
2. `slot_code` (if not configured attribute)
3. `slot_name` (if slot_code empty)
4. Skip event (no valid identifier)

**Admin UI**: Dropdown per integration
- Label: "Guest Authorization Attribute"
- Options: "Slot Code (4+ digits)", "Slot Name", "Last Four Digits"
- Default: "Slot Code (4+ digits)"

**Implementation**:
- Migration: `ALTER TABLE ha_integration_config ADD COLUMN auth_attribute TEXT DEFAULT 'slot_code'`
- Service: `RentalControlService.get_auth_identifier(event, integration_config)`

**File**: `src/captive_portal/integrations/rental_control_service.py`

**Approved**: 2025-10-26T14:54:00Z

---

## Decision D8: Event Expiry Cleanup

**Decision**: 7-day retention, daily 3 AM cleanup, vouchers remain valid

**Retention Policy**:
- **Duration**: 7 days post-checkout (after `end_utc`)
- **Rationale**: Supports dispute resolution, aligns with booking platform retention
- **Cleanup**: Daily at 3:00 AM local time (configurable)

**Cleanup Mechanism**:
- **Job**: Background task runs daily
- **Schedule**: Default 3:00 AM (configurable via env var `CLEANUP_HOUR=3`)
- **Query**: `DELETE FROM rental_control_events WHERE end_utc < (NOW() - INTERVAL 7 days)`
- **Audit**: Log cleanup count to AuditService

**Voucher Lifecycle**:
- Vouchers remain VALID after event cleanup
- Once created, voucher is independent of event
- Voucher expiry controlled by `expires_utc` field (not tied to event)

**Implementation**:
- Background task: `asyncio.create_task()` with daily schedule
- Cleanup service: `CleanupService.cleanup_expired_events()`
- Audit log: `audit.log(action="event.cleanup", meta={"deleted_count": N})`

**File**: `src/captive_portal/services/cleanup_service.py`

**Approved**: 2025-10-26T14:54:00Z

---

## Decision D9: End-of-Stay Grace Period

**Decision**: Configurable grace period for guest access after checkout

**Problem**: Guests checking out may need brief WiFi access for ride-sharing, final uploads, etc.

**Configuration**:
- **Default**: 15 minutes post-checkout
- **Maximum**: 30 minutes (hard limit)
- **Minimum**: 0 minutes (disable grace period)
- **Scope**: Per-integration configuration

**Database Schema Addition**:
```python
# HAIntegrationConfig model addition
checkout_grace_minutes: int = Field(default=15, ge=0, le=30)
```

**Behavior**:
- Grants created from Rental Control events extend `end_utc` by grace period
- Grace period added when creating voucher from event
- Example: Checkout 10:00 AM, 15 min grace → voucher valid until 10:15 AM
- Vouchers created manually (not from events) unaffected

**Implementation**:
```python
# When creating voucher from event
voucher_end = event.end_utc + timedelta(minutes=integration.checkout_grace_minutes)
voucher = VoucherService.create(
    duration_minutes=calculate_duration(event.start_utc, voucher_end),
    ...
)
```

**Admin UI**:
- Input: Number field per integration
- Label: "Checkout Grace Period (minutes)"
- Range: 0-30
- Default: 15
- Help text: "Guests retain WiFi access for this many minutes after checkout"

**Validation**:
- Min: 0 (no grace period)
- Max: 30 (hard limit via Pydantic validator)
- Error: "Grace period must be 0-30 minutes"

**Migration**:
```sql
ALTER TABLE ha_integration_config
ADD COLUMN checkout_grace_minutes INTEGER DEFAULT 15
CHECK (checkout_grace_minutes >= 0 AND checkout_grace_minutes <= 30);
```

**Files**:
- Model: `src/captive_portal/models/ha_integration_config.py`
- Service: `src/captive_portal/integrations/rental_control_service.py`
- Migration: `alembic/versions/XXX_add_checkout_grace.py`

**Approved**: 2025-10-26T14:54:00Z

---

## Summary of Approved Decisions

| Decision | Summary | Implementation Priority |
|----------|---------|------------------------|
| **D5** | HA integration via REST API (httpx) | Phase 3 - High |
| **D6** | Poll all integrations, 60s batch, exponential backoff | Phase 3 - High |
| **D7** | Per-integration auth attribute (default slot_code) | Phase 3 - High |
| **D8** | 7-day event retention, daily 3 AM cleanup | Phase 3 - Medium |
| **D9** | 0-30 min checkout grace (default 15 min) | Phase 3 - High |

## Database Schema Changes Required

### HAIntegrationConfig Model Updates

```python
class HAIntegrationConfig(SQLModel, table=True):
    # ... existing fields ...

    # D7: Guest auth attribute selection
    auth_attribute: str = Field(
        default="slot_code",
        description="Attribute to use for guest authorization: slot_code, slot_name, last_four"
    )

    # D9: Checkout grace period
    checkout_grace_minutes: int = Field(
        default=15,
        ge=0,
        le=30,
        description="Minutes of WiFi access after checkout (0-30)"
    )
```

### New Table: RentalControlEvent (for D8 cleanup)

```python
class RentalControlEvent(SQLModel, table=True):
    """Cached Rental Control event data for voucher creation."""
    id: Optional[int] = Field(default=None, primary_key=True)
    integration_id: int = Field(foreign_key="ha_integration_config.id")
    event_index: int  # 0-N from sensor
    slot_name: Optional[str]
    slot_code: Optional[str]
    last_four: Optional[str]
    start_utc: datetime
    end_utc: datetime
    raw_attributes: str  # JSON blob of full event attributes
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

**Next Steps**:
1. Update `HAIntegrationConfig` model with new fields
2. Create migration for schema changes
3. Implement `HAClient` (REST API wrapper)
4. Implement `HAPoller` (60s polling service)
5. Implement `RentalControlService` (event processing, auth attribute selection)
6. Implement `CleanupService` (7-day retention)
7. Update Phase 3 tasks with new requirements

**Phase 3 Ready to Begin**: ✅

---

---

## Decision D10: Booking Code Case Sensitivity

**Decision**: Case-insensitive matching, case-sensitive storage and display

**Problem**: Guests may mistype case on mobile devices; admin needs original case for cross-reference with booking platforms.

**Implementation**:

**Matching Strategy**:
- Guest input normalized for lookup: `LOWER(guest_input) == LOWER(stored_value)`
- SQL: `WHERE LOWER(slot_code) = LOWER(:input)` or `func.lower()` in SQLAlchemy
- Whitespace trimmed from input

**Storage Strategy**:
- Store: Original case from Rental Control (slot_code, slot_name, last_four)
- No normalization on write
- Preserve exact string for admin cross-reference

**Display Strategy**:
- Admin UI: Show original case
- Audit logs: Log original case
- Error messages: Display original case when referencing booking codes

**Example Flow**:
1. Rental Control provides: `slot_code="ABC123"`
2. Guest enters: `"aBc123"`
3. Lookup: `LOWER("aBc123") == LOWER("ABC123")` → Match found
4. Display in admin: `"ABC123"` (original)
5. Audit log: `booking_code="ABC123"` (original)

**Service Changes**:
```python
# booking_code_validator.py
def validate_code(user_input: str, integration: HAIntegrationConfig) -> Optional[RentalControlEvent]:
    normalized_input = user_input.strip()
    # Case-insensitive query
    query = db.query(RentalControlEvent).filter(
        RentalControlEvent.integration_id == integration.id,
        func.lower(getattr(RentalControlEvent, integration.auth_attribute)) == normalized_input.lower()
    )
    return query.first()  # Returns event with original case
```

**Database Impact**: None (no schema changes)

**UI Impact** (Phase 4):
- Guest input field: Accept any case, normalize for lookup
- Admin display: Show original case in grants list
- Error messages: Reference original case when displaying codes

**File**: `src/captive_portal/services/booking_code_validator.py`

**Approved**: 2025-10-26T16:49:00Z

---

## Decision D11: UI Scope for Phase 3

**Decision**: Keep Phase 3 backend-focused; defer UI to Phase 4

**Problem**: Expanded Phase 3 scope introduces new UI needs not originally planned for this phase:
1. HA Integration configuration form (admin)
2. Guest booking code authorization form
3. Enhanced grants display (show booking identifier, grace period, integration)

**Options Considered**:
- **Option A (CHOSEN)**: Backend-only in Phase 3; REST APIs tested via integration tests; UI in Phase 4
- **Option B**: Minimal UI now (basic forms); polish in Phase 4
- **Option C**: Full UI in Phase 3 (extends timeline)

**Rationale for Option A**:
- Maintains clean phase separation (backend → UI)
- Prevents scope creep and timeline extension
- Testable via integration tests (API validation sufficient)
- Aligns with original plan (Phase 4 = Admin UI, Phase 5 = Guest Authorization UI)
- Reduces risk of introducing UI bugs while backend still stabilizing

**Phase 3 Deliverables**:
- REST API endpoints:
  - `POST /api/admin/integrations` (create/update HAIntegrationConfig)
  - `GET /api/admin/integrations` (list configurations)
  - `POST /api/guest/authorize` (booking code validation)
  - `GET /api/admin/grants` (list grants with booking identifiers)
- Backend services: HAClient, HAPoller, RentalControlService, CleanupService
- Database models: HAIntegrationConfig, RentalControlEvent
- Integration tests: API contract validation, error scenarios

**Phase 4 Deliverables** (UI implementation):
- Admin forms for HA integration configuration
- Guest booking code authorization form
- Enhanced grants display
- Theme integration for guest-facing pages
- CSRF protection and session security

**Impact on Tasks**:
- Phase 3 focuses on T0303-T0327 (backend services, models, tests)
- Phase 4 adds new UI tasks: T0422-T0425 (HA config UI, booking auth UI, grants display)

**Files**:
- Phase 3: Backend services and API routes only
- Phase 4: Web templates, forms, and UI routes

**Approved**: 2025-10-26T16:49:00Z

---

## Summary of All Approved Decisions

| Decision | Summary | Implementation Phase | Priority |
|----------|---------|---------------------|----------|
| **D5** | HA integration via REST API (httpx) | Phase 3 | High |
| **D6** | Poll all integrations, 60s batch, exponential backoff | Phase 3 | High |
| **D7** | Per-integration auth attribute (default slot_code) | Phase 3 | High |
| **D8** | 7-day event retention, daily 3 AM cleanup | Phase 3 | Medium |
| **D9** | 0-30 min checkout grace (default 15 min) | Phase 3 | High |
| **D10** | Case-insensitive match, case-sensitive store/display | Phase 3 | High |
| **D11** | Backend-only Phase 3; UI deferred to Phase 4 | Phase 3/4 | High |

---

**Approved By**: User
**Approval Date**: 2025-10-26T16:49:00Z
**Documented By**: Implementation Agent
