# Quickstart: Voucher Auto-Purge and Admin Purge

**Feature Branch**: `011-voucher-purge`
**Date**: 2025-07-22

## Overview

This feature adds automatic and manual purging of expired/revoked vouchers to the captive portal. It introduces a new timestamp field (`status_changed_utc`) on vouchers, a background auto-purge that runs on admin page load, and an admin UI for on-demand purge.

## Prerequisites

- Python 3.12+
- `uv` package manager installed
- Repository cloned and on the `011-voucher-purge` branch

## Setup

```bash
# Clone and switch to feature branch
git checkout 011-voucher-purge

# Install dependencies
uv sync --group dev

# Verify setup
uv run pytest --co -q  # list collected tests
```

## Key Files

| File | Purpose |
|------|---------|
| `addon/src/captive_portal/models/voucher.py` | Voucher model with new `status_changed_utc` field |
| `addon/src/captive_portal/persistence/database.py` | Migration for `status_changed_utc` column + backfill |
| `addon/src/captive_portal/persistence/repositories.py` | New `count_purgeable()`, `purge()`, `nullify_voucher_references()` methods |
| `addon/src/captive_portal/services/voucher_service.py` | Updated to set `status_changed_utc` on status transitions |
| `addon/src/captive_portal/services/voucher_purge_service.py` | New service for auto-purge and manual purge orchestration |
| `addon/src/captive_portal/api/routes/vouchers_ui.py` | Admin route handlers for lazy auto-purge + manual purge UI |
| `addon/src/captive_portal/web/templates/admin/vouchers.html` | Admin template with purge form section |

## Development Workflow

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Specific test file
uv run pytest tests/unit/services/test_voucher_purge_service.py -v

# Integration tests only
uv run pytest tests/integration/ -v

# With coverage
uv run pytest --cov=captive_portal --cov-report=term-missing
```

### Running Linters

```bash
# Ruff (linting + formatting)
uv run ruff check addon/src/ tests/
uv run ruff format --check addon/src/ tests/

# mypy (type checking)
uv run mypy addon/src/ tests/

# interrogate (docstring coverage)
uv run interrogate addon/src/
```

### Testing Manually

1. Start the development server:
   ```bash
   cd addon && uv run uvicorn captive_portal.app:app --reload --port 8080
   ```
2. Navigate to `http://localhost:8080/admin/vouchers/`
3. Create vouchers, then use the "Purge Expired/Revoked Vouchers" section to test manual purge

## Implementation Phases

### Phase 1: Model & Migration (status_changed_utc)
- Add `status_changed_utc` field to `Voucher` model
- Add migration function in `database.py`
- Update `expire_stale_vouchers()` and `revoke()` to set the timestamp
- TDD: unit tests for model field, migration, and timestamp setting

### Phase 2: Purge Service & Auto-Purge
- Create `VoucherPurgeService` with `auto_purge()` method
- Add `count_purgeable()` and `purge()` to `VoucherRepository`
- Add `nullify_voucher_references()` to `AccessGrantRepository`
- Wire auto-purge into `list_vouchers_admin` route handler
- TDD: unit tests for service and repository methods

### Phase 3: Admin Manual Purge UI
- Add purge form to `vouchers.html` template
- Add `purge-preview` and `purge-confirm` POST endpoints
- Add input validation (non-negative integer)
- TDD: integration tests for full purge UI flow

## Architecture Notes

- **Lazy triggering**: Auto-purge runs on admin voucher page load, after `expire_stale_vouchers()`. No background scheduler needed.
- **Batch SQL**: Purge uses single-statement SQL DELETE for efficiency. Grant nullification uses single-statement SQL UPDATE.
- **Transaction safety**: Grant nullification and voucher deletion occur in the same transaction for atomicity.
- **Audit trail**: Both auto-purge and manual purge log a single summary audit entry (not per-voucher).
- **Idempotency**: Purging already-deleted vouchers is a no-op (WHERE clause filters naturally). Re-running status transitions does not overwrite `status_changed_utc`.
