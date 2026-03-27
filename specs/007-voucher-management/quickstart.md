SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Voucher Management

**Feature**: 007-voucher-management | **Date**: 2025-07-18

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on `007-voucher-management` branch

## Setup

```bash
# Clone and switch to feature branch
cd <your-clone>
git checkout 007-voucher-management

# Install dependencies (dev group includes test tools)
uv sync --group dev
```

## Run Tests

```bash
# Run all tests
uv run pytest tests/ -x -q

# Run only unit tests
uv run pytest tests/unit/ -x -q

# Run only integration tests
uv run pytest tests/integration/ -x -q

# Run with coverage
uv run pytest tests/ --cov=captive_portal --cov-report=term-missing

# Run specific test files for this feature (once implementation is complete)
# Unit tests:
# uv run pytest tests/unit/routes/test_vouchers_ui.py -x -v
# uv run pytest tests/unit/services/test_voucher_service_revoke.py -x -v
# uv run pytest tests/unit/services/test_voucher_service_delete.py -x -v
#
# Integration tests:
# uv run pytest tests/integration/test_admin_voucher_revoke.py -x -v
# uv run pytest tests/integration/test_admin_voucher_delete.py -x -v
# uv run pytest tests/integration/test_admin_voucher_bulk_ops.py -x -v
```

## Lint & Type Check

```bash
# Lint
uv run ruff check addon/src/ tests/

# Format check
uv run ruff format --check addon/src/ tests/

# Type check
uv run mypy addon/src/

# Docstring coverage (100% required, runs via pre-commit)
uv tool run interrogate addon/src/ -v
```

## Run Locally (for manual testing)

```bash
# Start the admin app on port 8080
uv run uvicorn captive_portal.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Admin vouchers page:
#   http://localhost:8080/admin/vouchers
#
# Manual test flow:
#   1. Log in at http://localhost:8080/admin/login
#   2. Create a voucher on the vouchers page
#   3. Verify revoke button is enabled for unused/active vouchers
#   4. Click revoke → verify status changes to "revoked"
#   5. Verify revoke button is now disabled
#   6. Create another voucher (do not redeem)
#   7. Click delete → verify voucher is removed from list
#   8. Create multiple vouchers
#   9. Select several via checkboxes
#  10. Click "Revoke Selected" → verify summary message
#  11. Select remaining → click "Delete Selected" → verify summary
```

## Key Files for This Feature

### Files to Modify
| File | Change |
|------|--------|
| `addon/src/captive_portal/api/routes/vouchers_ui.py` | Add POST revoke, delete, bulk-revoke, bulk-delete endpoints |
| `addon/src/captive_portal/services/voucher_service.py` | Add `revoke()`, `delete()` methods + error classes |
| `addon/src/captive_portal/persistence/repositories.py` | Add `VoucherRepository.delete()` method |
| `addon/src/captive_portal/web/templates/admin/vouchers.html` | Add action columns, checkboxes, bulk controls |
| `addon/src/captive_portal/web/themes/default/admin.css` | Add checkbox, bulk-action-bar styles |
| `tests/unit/routes/test_vouchers_ui.py` | Add revoke, delete, bulk endpoint tests |

### New Files to Create
| File | Purpose |
|------|---------|
| `tests/unit/services/test_voucher_service_revoke.py` | TDD tests for VoucherService.revoke() |
| `tests/unit/services/test_voucher_service_delete.py` | TDD tests for VoucherService.delete() |
| `tests/integration/test_admin_voucher_revoke.py` | Full-page revoke flow integration tests |
| `tests/integration/test_admin_voucher_delete.py` | Full-page delete flow integration tests |
| `tests/integration/test_admin_voucher_bulk_ops.py` | Bulk operations integration tests |
| `addon/src/captive_portal/web/themes/default/admin-vouchers.js` | Progressive enhancement for select-all checkbox |

## Development Workflow

Follow constitution-mandated TDD:

1. **Red**: Write a failing test for the next behavior
2. **Green**: Write minimum code to make the test pass
3. **Refactor**: Clean up while keeping tests green
4. **Lint**: `uv run ruff check` + `uv run mypy`
5. **Commit**: `git commit -s -m "Type(scope): Description"`

## Suggested Implementation Order

> **Note**: `specs/007-voucher-management/tasks.md` is the authoritative execution
> order. The summary below is a simplified overview.

1. **Phase 1 — Revoke (P1, MVP)**: `VoucherService.revoke()` + `POST /admin/vouchers/revoke/{code}` + template action buttons + tests
2. **Phase 2 — Delete (P2)**: `VoucherRepository.delete()` + `VoucherService.delete()` + `POST /admin/vouchers/delete/{code}` + template + tests
3. **Phase 3 — Bulk Operations (P3)**: Checkbox UI + `POST bulk-revoke` + `POST bulk-delete` + summary messages + select-all JS + tests
4. **Phase 4 — Polish**: Performance benchmarks, edge case hardening, full test sweep
