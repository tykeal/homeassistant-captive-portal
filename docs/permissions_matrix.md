<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# RBAC Permissions Matrix

**Feature**: FR-017 Role-Based Access Control
**Phase**: 2 (Core Services)
**Status**: Implemented

## Role Definitions

| Role | Description | Use Case |
|------|-------------|----------|
| **viewer** | Read-only access to health/status | Monitoring systems, dashboards |
| **auditor** | Read access to grants + audit logs | Compliance review, security auditing |
| **operator** | Manage grants, create vouchers | Daily operations, guest management |
| **admin** | Full access including user management | System administration, configuration |

## Permissions Matrix

### System Endpoints

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `internal.health.read` | ✅ | ✅ | ✅ | ✅ | Health check endpoint |

### Grant Management

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `grants.list` | ❌ | ✅ | ✅ | ✅ | View active/expired grants |
| `grants.extend` | ❌ | ❌ | ✅ | ✅ | Extend grant duration |
| `grants.revoke` | ❌ | ❌ | ✅ | ✅ | Revoke access grant |

### Voucher Management

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `vouchers.create` | ❌ | ❌ | ✅ | ✅ | Generate new voucher codes |
| `vouchers.redeem` | ❌ | ❌ | ✅ | ✅ | Guest redemption (portal) |

### Administration

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `admin.accounts.create` | ❌ | ❌ | ❌ | ✅ | Create admin users |
| `admin.accounts.list` | ❌ | ❌ | ❌ | ✅ | View admin accounts |

### Audit Logging

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `audit.entries.list` | ❌ | ✅ | ❌ | ✅ | Review audit logs |

### Configuration

| Action | viewer | auditor | operator | admin | Notes |
|--------|--------|---------|----------|-------|-------|
| `config.theming.update` | ❌ | ❌ | ❌ | ✅ | Update portal theme |

## Enforcement

**Deny-by-default**: Actions not explicitly listed in `ROLE_ACTIONS` are denied for all roles.

**Implementation**:
- Matrix defined in `src/captive_portal/security.py`
- Enforced by `src/captive_portal/middleware.py:rbac_enforcer()`
- Denials logged to audit log via `AuditService.log_rbac_denied()`

**Response**: HTTP 403 with error code `RBAC_FORBIDDEN`

## Testing

**Test Coverage**:
- `tests/integration/test_rbac_permission_matrix_allow.py`: Verify allowed actions
- `tests/integration/test_rbac_permission_matrix_deny.py`: Verify denials
- `tests/unit/test_security_matrix.py`: Unit test `is_allowed()` logic

**Test Strategy**:
1. Parametrized tests for each (role, action) combination
2. Verify 200 OK for allowed actions
3. Verify 403 Forbidden for denied actions
4. Verify deny-by-default (unknown actions rejected)

## Acceptance Criteria (FR-017)

✅ **AC1**: Four roles defined (viewer, auditor, operator, admin)
✅ **AC2**: Action-based permissions (not endpoint-based)
✅ **AC3**: Deny-by-default enforcement
✅ **AC4**: Matrix externalized (not hardcoded in routes)
✅ **AC5**: RBAC denials logged to audit log
✅ **AC6**: Integration tests cover allow + deny paths

## Future Enhancements

**Phase 3+** (out of scope for Phase 2):
- Dynamic role assignment (currently header-based stub)
- Session-based role resolution (from AdminUser.role)
- Resource-level permissions (e.g., "revoke own grants only")
- Custom roles (beyond the 4 predefined)

## Role Assignment

**Phase 2 Status**: Roles assigned via `X-Role` header (test/dev only)

**Phase 4 Target**:
- Roles resolved from authenticated admin session
- AdminUser.role field populated during login
- Session middleware injects role into request context

**Security Note**: `X-Role` header MUST NOT be trusted in production. Phase 4 will implement proper session-based role resolution with argon2 password hashing (D1 decision).

---

**Last Updated**: 2025-10-26
**Maintained By**: Implementation Team
**Related**: `spec.md` FR-017, `plan.md` Phase 2, `security.py`
