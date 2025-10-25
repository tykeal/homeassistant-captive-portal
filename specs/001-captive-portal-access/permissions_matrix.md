SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# RBAC Permissions Matrix (FR-017)

## Roles
- viewer: read-only access to health/status (future: read grants list without PII details)
- operator: viewer plus create/revoke/extend vouchers & grants
- auditor: viewer plus read full audit logs (no modification actions)
- admin: operator + auditor + manage admin accounts, configuration, theming

## Principles
- Deny-by-default: any action not explicitly granted results in 403 {"error":"forbidden","code":"RBAC_FORBIDDEN"}
- Action identifiers are stable strings `<domain>.<resource>.<verb>`
- Matrix is a pure data structure (no code side-effects) consumed by middleware
- Tests enumerate allow + deny cases (T0206, T0207)

## Matrix (Initial)
| Action | viewer | operator | auditor | admin |
|--------|--------|----------|---------|-------|
| internal.health.read | X | X | X | X |
| grants.list |  | X | X | X |
| grants.extend |  | X |  | X |
| grants.revoke |  | X |  | X |
| vouchers.redeem |  | X |  | X |
| vouchers.create |  | X |  | X |
| admin.accounts.create |  |  |  | X |
| admin.accounts.list |  |  |  | X |
| audit.entries.list |  |  | X | X |
| config.theming.update |  |  |  | X |

(Empty cell = deny)

## Acceptance Criteria (FR-017)
1. All actions enforced through single middleware dependency.
2. Unknown action lookups raise 500 at startup (test coverage) & never silently allow.
3. 100% of protected routes declare an action string or test fails.
4. Denied request returns 403 JSON with code RBAC_FORBIDDEN without stack trace in body.
5. Audit log entry emitted on every deny (role, action, path, correlation_id).
6. Matrix file change without corresponding tests (allow/deny) fails CI.
7. Adding new endpoint requires specifying action or CI fails.

## Test Plan Mapping
- Allow matrix: tests/integration/test_rbac_permission_matrix_allow.py validates positive set.
- Deny matrix: tests/integration/test_rbac_permission_matrix_deny.py validates negative set.
- Startup validation: unit test ensures matrix covers declared route actions.

## Future Extensions
- Attribute-based constraints (time-of-day, IP range) layer atop role grant.
- Dynamic role assignment or custom roles (Phase >=6 decision).
