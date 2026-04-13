SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: VLAN-Based Authorization Isolation

**Feature**: 009-vlan-auth-isolation
**Date**: 2025-07-14
**Status**: Complete

## Research Tasks

### R1: VLAN Allowlist Storage Strategy — JSON Column vs. Separate Table

**Context**: Each `HAIntegrationConfig` and `Voucher` needs to store a set of allowed VLAN IDs (integers 1–4094). Two approaches: a dedicated `VLANMapping` junction table or a JSON column on each entity.

**Decision**: Use a JSON column (`allowed_vlans`) on both `HAIntegrationConfig` and `Voucher` models. Store as a JSON-serialized list of integers (e.g., `[50, 51, 55]`). An empty list or `null` means "no VLAN restriction" (backward compatible).

**Rationale**:
- VLAN allowlists are small (typically 1–5 entries per entity) and always loaded with the parent entity — there is no use case for querying VLANs independently across entities.
- SQLModel supports JSON columns via `sa_column=Column(JSON)`. SQLite handles JSON natively since 3.38 (Python 3.12 bundles SQLite 3.40+).
- A junction table adds JOIN complexity for every authorization check without meaningful benefit at this scale. It would also require a new repository class, migration logic, and more test surface area.
- The JSON column can be validated on read by Pydantic/SQLModel field validators, ensuring type safety at the application layer.
- Existing patterns in the codebase use JSON columns for metadata (e.g., `AuditLog.meta` stores a JSON dict).

**Alternatives considered**:
1. **Separate `VLANMapping` table** with (`entity_type`, `entity_id`, `vlan_id`) rows. Rejected because the N:1 relationship is always loaded with the parent, the allowlists are tiny, and a junction table adds ORM complexity (relationship declarations, cascade deletes) disproportionate to the data size.
2. **Comma-separated string column** (e.g., `"50,51,55"`). Rejected because it requires manual parsing/serialization and loses type safety. JSON column is the standard SQLModel/SQLAlchemy approach.

---

### R2: VLAN Validation Insertion Point in Authorization Flow

**Context**: The `handle_authorization()` function in `guest_portal.py` processes both voucher and booking code paths. VLAN validation must be inserted at the right point in the flow.

**Decision**: Insert VLAN validation **after** code validation and grant creation but **before** controller authorization. Specifically, after the `try/except` block that creates the `AccessGrant` (line ~644) and before the `_authorize_with_controller()` call (line ~757).

**Rationale**:
- Validating after code recognition ensures we know which integration (booking path) or voucher (voucher path) to check the VLAN against.
- Validating before controller authorization avoids sending a grant to the Omada controller that will be immediately rejected, saving unnecessary controller API calls.
- The grant is created in PENDING status before VLAN validation. If VLAN validation fails, the grant can either be revoked/deleted or left as FAILED for audit trail purposes.
- The `vid` form parameter is already available and sanitized by `_truncate(vid, 8)`.

**Flow change**:
```
[existing] Code validation → Grant creation (PENDING)
[NEW]      → VLAN validation (check vid against integration/voucher allowlist)
[existing] → Controller authorization → Grant status → ACTIVE/FAILED
```

**Error handling**: On VLAN mismatch, set `grant.status = GrantStatus.FAILED`, log to audit with `outcome="denied"` and `meta.reason="vlan_mismatch"`, raise `HTTPException(403)` with vague message "This code is not valid for your network." per FR-004/spec assumption.

**Alternative considered**: Validating VLAN before grant creation. Rejected because the grant record is useful for the audit trail even on rejection — it records the attempted MAC, code, and VLAN, providing forensic value.

---

### R3: VID Parameter Parsing and Validation

**Context**: The `vid` parameter arrives from the Omada controller redirect as a query string value (string). It needs to be parsed and validated as an IEEE 802.1Q VLAN ID (integer 1–4094).

**Decision**: Parse `vid` as an integer in the `VlanValidationService`. If `vid` is missing, empty, non-numeric, or outside the 1–4094 range, treat it as "no VID present." When an integration/voucher has VLANs configured but the device has no valid VID, reject authorization per FR-006.

**Rationale**:
- The Omada controller is expected to provide a valid integer VID, but edge cases (malformed redirect, URL manipulation) require defensive parsing.
- IEEE 802.1Q reserves VLAN 0 (priority tagging only) and VLAN 4095. The spec explicitly states the valid range is 1–4094 (FR-002).
- The existing code stores `vid` as `Optional[str]` on the grant — parsing to int happens only in the validation service, not in the model.

**Validation rules**:
- `vid` is `None` or empty string → no VID present
- `vid` is non-numeric (e.g., "abc", "50a") → no VID present (treat as malformed)
- `vid` parses to int but is < 1 or > 4094 → no VID present (out of range)
- `vid` parses to valid int in 1–4094 → valid VID

---

### R4: Backward Compatibility Strategy

**Context**: Existing deployments have no VLAN configuration. The upgrade path must not break any current authorization flow (User Story 4, FR-005).

**Decision**: VLAN validation is skipped entirely when the integration/voucher has an empty `allowed_vlans` list (or `null`). The validation service returns "allowed" immediately without examining the device's VID.

**Rationale**:
- This matches the spec requirement (FR-005): "System MUST skip VLAN validation entirely when an integration has no allowed VLANs configured (empty list)."
- Null/empty JSON column is the natural default for the migration — existing rows will have `NULL` for `allowed_vlans`, which the service interprets as "unrestricted."
- No configuration action is required from administrators on upgrade.

**Migration strategy**: The SQLite migration adds `allowed_vlans` as a nullable JSON column with no default value. Existing rows get `NULL`, which is semantically equivalent to "no restriction." New rows created through the admin API will default to an empty list `[]`.

---

### R5: Admin VLAN Configuration API Design

**Context**: Administrators need to configure VLAN allowlists for integrations and optionally for vouchers. The existing integration API uses REST CRUD with Pydantic request/response schemas.

**Decision**: Extend the existing `IntegrationConfigCreate`, `IntegrationConfigUpdate`, and `IntegrationConfigResponse` schemas with an `allowed_vlans: list[int]` field. For vouchers, extend `CreateVoucherRequest` and `VoucherResponse` with an optional `allowed_vlans: list[int] | None` field.

**Rationale**:
- Adding to existing schemas (rather than creating separate VLAN endpoints) keeps the API surface minimal and follows the established pattern.
- VLAN configuration is an attribute of the integration/voucher, not a separate entity — it belongs in the same CRUD operations.
- Validation (1–4094 range, no duplicates) is enforced by Pydantic field validators on the request schemas.

**API changes**:
- `POST /api/integrations` — accepts optional `allowed_vlans: list[int]` (default `[]`)
- `PATCH /api/integrations/{id}` — accepts optional `allowed_vlans: list[int]`
- `GET /api/integrations` — response includes `allowed_vlans` field
- `POST /api/vouchers/` — accepts optional `allowed_vlans: list[int] | None` (default `None`)
- `GET /api/vouchers/` (list) and `GET /api/vouchers/{code}` — response includes `allowed_vlans`

**Validation rules on request**:
- Each VLAN ID must be an integer in range 1–4094
- Duplicate VLAN IDs are silently deduplicated
- The same VLAN ID may appear on multiple integrations (FR-012)

---

### R6: Audit Log Integration for VLAN Validation

**Context**: FR-010 requires recording VLAN validation results (allowed/rejected, VLAN ID checked) in the audit log for every authorization attempt.

**Decision**: Extend the existing `audit_service.log()` call's `meta` dict with VLAN validation fields: `vlan_id` (the device's VID), `vlan_allowed_list` (the integration/voucher's configured VLANs), and `vlan_result` (`"allowed"`, `"rejected"`, or `"skipped"`).

**Rationale**:
- The existing audit infrastructure already stores arbitrary metadata as a JSON dict. Adding VLAN fields requires no schema changes to `AuditLog`.
- Recording both the device VID and the allowlist provides complete forensic context for any authorization decision.
- "Skipped" result covers the backward-compatible case where no VLANs are configured.

**Audit log meta structure** (new fields):
```json
{
  "vlan_id": "50",
  "vlan_allowed_list": [50, 51],
  "vlan_result": "allowed"
}
```

---

### R7: SQLite JSON Column with SQLModel

**Context**: SQLModel's `Field()` does not natively support JSON columns in the same way as vanilla SQLAlchemy's `Column(JSON)`. Need to confirm the correct pattern for declaring a JSON column on an SQLModel table model.

**Decision**: Use `sa_column=Column(JSON, nullable=True)` in the SQLModel field declaration, with a Pydantic field type of `list[int] | None`. Provide a `@field_validator` for input validation (range 1–4094, deduplication).

**Rationale**:
- The existing `AuditLog.meta` field in this project uses the pattern `meta: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))` — this is the established convention.
- SQLite's JSON1 extension is built-in for Python 3.12+ (SQLite 3.40+). No additional setup needed.
- SQLModel transparently serializes/deserializes `list[int]` to/from JSON when using `Column(JSON)`.

**Implementation pattern**:
```python
from sqlalchemy import Column, JSON

class HAIntegrationConfig(SQLModel, table=True):
    allowed_vlans: list[int] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def validate_vlans(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        return sorted(set(int(x) for x in v if 1 <= int(x) <= 4094))
```

---

### R8: Multi-Integration Booking Code Resolution with VLAN

**Context**: The current booking code path queries `select(HAIntegrationConfig).limit(1)` — it only supports a single integration. The spec edge case asks: "What happens if the same booking code matches events across multiple integrations with different VLAN allowlists?"

**Decision**: The current single-integration lookup is a known limitation. For VLAN isolation to work correctly with multiple integrations, the booking code path must iterate all integrations, find matching events, and validate the device's VLAN against each matching integration's allowlist. The first integration that matches both the booking code AND the VLAN should be used.

**Rationale**:
- With VLAN isolation, the VLAN acts as an additional discriminator — a booking code on VLAN 50 should match the integration configured for VLAN 50, not the one for VLAN 51.
- The current `limit(1)` query is inadequate when multiple integrations exist. This must be refactored to query all integrations and attempt validation against each.
- This ordering (check all integrations, find event match, then validate VLAN) ensures the spec edge case is handled correctly: "The system should use the integration that owns the matching event and validate against that integration's VLANs."

**Implementation approach**:
1. Query all `HAIntegrationConfig` records (typically < 20)
2. For each integration, attempt `booking_validator.validate_code(code, integration)`
3. Collect all (integration, event) matches
4. If exactly one match: validate VLAN against that integration's allowlist
5. If multiple matches: filter by VLAN — use the integration whose allowlist includes the device's VID
6. If no VLAN-compatible match after filtering: reject with VLAN error
7. If no matches at all: standard "Booking not found" error

**Alternative considered**: Adding a VLAN pre-filter before booking code lookup (only query integrations whose VLANs match the device's VID). Rejected because it would break the "unconfigured integrations skip VLAN checks" rule — an integration with no VLANs configured should still match any VID.
