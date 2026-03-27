SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Voucher Management

**Feature**: 007-voucher-management | **Date**: 2025-07-18

## R1: Revoke Eligibility — Expiry Check Strategy

### Decision
Voucher revoke eligibility is determined by a real-time UTC comparison (`now <= voucher.expires_utc`) in `VoucherService.revoke()`, not by the persisted `VoucherStatus.EXPIRED` flag. The service method rejects revocation when `now > expires_utc` with a dedicated `VoucherExpiredError`. The UI route disables the revoke button when the computed status is "expired".

### Rationale
The spec (FR-001, FR-005) and the normative expiry definition explicitly require time-based eligibility:
> *"revoke eligibility MUST, at a minimum, enforce this time-based expiry check and MUST NOT rely solely on a stored status flag."*

`Voucher.expires_utc` is a `@computed_field` property (`created_utc + duration_minutes`, floored to minute). It is reliable at query time but not stored as a database column, so the check must occur in Python. This is consistent with how the grants page re-computes grant status at render time.

### Alternatives Considered
1. **Check stored `VoucherStatus.EXPIRED` flag**: Rejected — the spec normative definition explicitly forbids relying solely on a stored flag. The flag may not be updated promptly (no background process transitions vouchers to EXPIRED).
2. **Add `expires_utc` as a persisted column and check in SQL**: Rejected — would require a schema migration and breaks the existing computed-field pattern. The Python-level check is sufficient given the small voucher volume (~200).
3. **Allow revoking expired vouchers (no expiry check)**: Rejected — FR-005 explicitly forbids it, as revocation of expired vouchers would be misleading.

---

## R2: Revoke Implementation — Service Method Pattern

### Decision
Add `async VoucherService.revoke(code: str) -> Voucher` modelled on the existing `GrantService.revoke()` pattern:
1. Fetch voucher by code via `VoucherRepository.get_by_code()`
2. Raise `VoucherNotFoundError` if not found
3. If already revoked → return immediately (idempotent, per FR-004)
4. Compute expiry: if `now > voucher.expires_utc` → raise `VoucherExpiredError` (FR-005)
5. Set `voucher.status = VoucherStatus.REVOKED`
6. Commit and return

### Rationale
This mirrors `GrantService.revoke()` exactly: idempotent for already-revoked entities, validation before state change, single commit. The voucher model already has the `REVOKED` enum value. No schema change is needed because the existing `status` column already supports it.

### Implementation Detail
The revoke method accepts any voucher in `UNUSED` or `ACTIVE` status (per FR-001) that has not expired. The status transitions are:
- `UNUSED` → `REVOKED` (admin cancels before any redemption)
- `ACTIVE` → `REVOKED` (admin cancels after redemption)
- `REVOKED` → `REVOKED` (no-op, idempotent)
- `EXPIRED` → rejected (not eligible)

### Alternatives Considered
1. **Separate revoke methods per status (revoke_unused, revoke_active)**: Rejected — unnecessary complexity; a single method with internal validation is cleaner.
2. **Revoke via repository method (repo.revoke)**: Rejected — business logic (expiry check, idempotency) belongs in the service layer, not the repository.

---

## R3: Delete Implementation — Hard Delete with Redemption Guard

### Decision
Add `async VoucherService.delete(code: str) -> None`:
1. Fetch voucher by code via `VoucherRepository.get_by_code()` (used for not-found handling and better error messaging).
2. Raise `VoucherNotFoundError` if not found.
3. Optionally, if `voucher.redeemed_count > 0` → raise `VoucherRedeemedError` (FR-008) for a clearer, pre-emptive error. This check is an optimization only and is **not** the concurrency guard.
4. Call `VoucherRepository.delete(code)` which performs an atomic `DELETE FROM voucher WHERE code = ? AND redeemed_count = 0` and returns `True` iff a row was deleted.
5. If `VoucherRepository.delete(code)` returns `False`, perform a follow-up `VoucherRepository.get_by_code(code)` in the same transaction to disambiguate:
   - If the voucher is no longer found → treat as concurrently deleted and raise `VoucherNotFoundError`.
   - If the voucher is still present → raise `VoucherRedeemedError` (covers the FR-010 race where redemption occurs between the read in step 1 and the delete).
6. Commit.

Add `VoucherRepository.delete(code: str) -> bool` that issues the predicate delete (`WHERE redeemed_count = 0`) and returns `True` only when the voucher was never redeemed and has been removed.

### Rationale
FR-006 requires deletion only for never-redeemed vouchers. FR-007 specifies permanent removal. FR-009 explicitly allows deletion of revoked-but-never-redeemed vouchers. The guard checks `redeemed_count == 0` at the database level via an atomic predicate delete, and the follow-up lookup in step 5 distinguishes between concurrent deletion (treated as not found) and late redemption (treated as redeemed). Together, these cover all cases and prevent the FR-010 race:
- Unused (redeemed_count=0): deletable ✓
- Revoked, never redeemed (redeemed_count=0): deletable ✓ (FR-009)
- Active (redeemed_count>0): not deletable ✗
- Revoked, previously redeemed (redeemed_count>0): not deletable ✗
- Expired (redeemed_count>0): not deletable ✗

The service captures the required voucher fields (status, booking_ref) before attempting the hard delete. The audit log entry is written only after the delete has been confirmed successful, using the captured snapshot values. This prevents orphaned audit entries when the predicate-based delete fails.

### Alternatives Considered
1. **Soft delete (mark as deleted, keep record)**: Rejected — spec explicitly requires permanent removal (FR-007) and the assumption section states "Voucher deletion is a hard delete (permanent removal), not a soft delete."
2. **Check status instead of redeemed_count**: Rejected — `redeemed_count` is the definitive indicator of whether a voucher was ever used. Status alone is insufficient because a revoked voucher may or may not have been redeemed.
3. **Cascade delete to audit logs**: Rejected — audit logs are independent entities and must be preserved for compliance.

---

## R4: Delete Race Condition — Concurrent Redemption Guard (FR-010)

### Decision
Use an atomic, predicate-based delete to guard against concurrent redemption. The `VoucherService.delete()` method delegates to `VoucherRepository.delete()`, which issues a single `DELETE` statement scoped by both the voucher identifier and the eligibility condition (`WHERE code = :code AND redeemed_count = 0`). It then checks the affected row count:

- If exactly one row was deleted, the voucher was still unredeemed and the hard delete succeeds.
- If zero rows were deleted, the service performs a follow-up lookup by code to disambiguate:
  - If the voucher no longer exists, it returns a "not found" response as per the route contract.
  - If the voucher still exists but no longer satisfies `redeemed_count = 0`, it returns the FR-010 error ("voucher has been redeemed and can no longer be deleted"; the UI copy may explain that it may have been redeemed after the page was loaded).

### Rationale
FR-010 requires: "System MUST reject a delete request if, at delete processing time, the voucher is already redeemed, displaying an explanatory error message (for example, indicating that it may have been redeemed after the page was loaded)." A simple "re-read then unconditional delete" leaves a race window between the final eligibility check and the delete statement, during which a concurrent redemption can increment `redeemed_count` and still be deleted.

By encoding the eligibility check (`redeemed_count = 0`) directly into the `DELETE` predicate and verifying that exactly one row was affected, the check and delete become a single atomic database operation. In SQLite, this is executed under its normal write-serialization rules; no additional client-side locking is required to prevent a concurrent redemption from slipping between the check and the delete.

### Alternatives Considered
1. **Optimistic locking with version field**: Rejected — adds schema complexity; the predicate-based delete already provides a lightweight form of optimistic concurrency.
2. **Row-level lock (SELECT FOR UPDATE)**: Rejected — SQLite does not support row-level locks; the atomic `DELETE ... WHERE redeemed_count = 0` pattern achieves the necessary protection.
3. **Pass redeemed_count from form as a hidden field and compare**: Rejected — client-supplied values cannot be trusted for security-critical decisions.

---

## R5: Bulk Operations — Sequential Processing with Summary

### Decision
Bulk revoke and bulk delete process vouchers sequentially in a single request, collecting per-voucher outcomes into a summary. New endpoints:
- `POST /admin/vouchers/bulk-revoke` — form field `codes` (list of voucher codes)
- `POST /admin/vouchers/bulk-delete` — form field `codes` (list of voucher codes)

Each endpoint iterates over the submitted codes, loads the corresponding voucher (if any), and then:
- For bulk revoke: if the voucher is already revoked, it is counted as "skipped (already revoked)" without calling `revoke()` to enable accurate skip counting; otherwise the handler calls the existing single-voucher `revoke()` method and catches domain exceptions (e.g., `VoucherExpiredError`) to skip other ineligible vouchers.
- For bulk delete: the handler calls the existing single-voucher `delete()` method and catches domain exceptions (e.g., `VoucherRedeemedError`) to skip ineligible vouchers; missing vouchers are counted as "skipped (not found)".

The handler accumulates per-voucher outcomes into counters used to build the summary message.

### Rationale
The spec (FR-013, FR-014) requires processing "each individually and skipping ineligible ones." This naturally maps to a loop calling the single-operation service methods. The pre-check for "already revoked" status avoids a redundant (idempotent) service call and enables accurate skip counting in the summary. The summary (FR-015) reports counts: "Revoked N vouchers, skipped M (expired: X, already revoked: Y)" or "Deleted N vouchers, skipped M (redeemed: X, not found: Y)".

Processing within a single HTTP request is acceptable because:
- Typical scale: 20–200 vouchers (SC-003 targets 20 in 10 seconds)
- Each operation is a single DB read + optional write
- SQLite write latency is sub-millisecond for small records

### Transaction Strategy
Each individual voucher operation commits independently (matching the single-operation pattern). This ensures that if the request is interrupted (e.g., timeout), already-processed vouchers retain their new state. A partial-success summary is better than an all-or-nothing approach for bulk operations.

### Alternatives Considered
1. **Background task/job queue**: Rejected — over-engineering for 20–200 items; adds infrastructure complexity.
2. **Single transaction for all vouchers**: Rejected — if one fails, all roll back. The spec expects partial success with skip reporting.
3. **Client-side iteration (one AJAX call per voucher)**: Rejected — violates "forms must work without JS" constraint. Also creates N HTTP round trips.

---

## R6: UI Selection Mechanism — Checkbox Forms Without JS

### Decision
Add a checkbox column to the voucher table with a master "select all" checkbox. Checkboxes are standard HTML `<input type="checkbox" name="codes" value="{code}">` inside a `<form>` element. Bulk action buttons (`Revoke Selected`, `Delete Selected`) submit the form.

The "select all" checkbox uses a small external JS file (`admin-vouchers.js`) for progressive enhancement, but the form works without JS — the user can manually check individual vouchers and submit.

### Rationale
FR-011 requires selection checkboxes. FR-012 requires "select all." The spec assumption states: "Bulk operations add selection UI on top of the existing table without redesigning the page layout."

HTML checkboxes with `name="codes"` submit as a list of values in form data. This is the simplest server-compatible approach and works without JavaScript. The "select all" checkbox behavior (checking/unchecking all visible checkboxes) requires JS but is a progressive enhancement — the form still submits correctly without it.

### Template Structure
```html
<form method="POST" id="bulk-form">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <div class="bulk-action-bar">
    <button formaction="{{ rp }}/admin/vouchers/bulk-revoke" type="submit"
            class="btn btn-warning">Revoke Selected</button>
    <button formaction="{{ rp }}/admin/vouchers/bulk-delete" type="submit"
            class="btn btn-danger">Delete Selected</button>
  </div>
  <table>
    <thead>
      <tr>
        <th><input type="checkbox" id="select-all" aria-label="Select all vouchers"></th>
        ...existing headers...
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for voucher in vouchers %}
      <tr>
        <td><input type="checkbox" name="codes" value="{{ voucher.code }}" aria-label="Select voucher {{ voucher.code }}"></td>
        ...existing columns...
        <td>
          <!-- Individual action buttons use formaction to target single-voucher endpoints (see R7) -->
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</form>
```

Using `formaction` on the submit buttons allows two different POST targets within the same form, avoiding duplicate checkbox sets.

### Alternatives Considered
1. **Separate form per bulk action (duplicate checkboxes)**: Rejected — requires duplicating all checkboxes or JS to copy selections. The `formaction` attribute is widely supported (HTML5).
2. **AJAX-based bulk operations**: Rejected — violates "forms must work without JS."
3. **Server-side pagination with select-across-pages**: Rejected — spec says "select all visible vouchers" (FR-012), not all vouchers across pages.

---

## R7: Individual Action Buttons — `formaction` Within the Bulk Form

### Decision
Add per-row action buttons for revoke and delete that use `formaction` attributes to target single-operation endpoints. These buttons live inside the single bulk `<form>` element (from R6), avoiding nested `<form>` tags which are invalid HTML:
```html
<td>
  <button type="submit"
          formaction="{{ rp }}/admin/vouchers/revoke/{{ voucher.code }}"
          class="btn btn-warning"
          {% if not voucher_actions[voucher.code].can_revoke %}disabled{% endif %}>
    Revoke
  </button>
  <button type="submit"
          formaction="{{ rp }}/admin/vouchers/delete/{{ voucher.code }}"
          class="btn btn-danger"
          {% if not voucher_actions[voucher.code].can_delete %}disabled{% endif %}>
    Delete
  </button>
</td>
```

### Rationale
The grants page uses separate per-row `<form>` elements for extend/revoke buttons. However, vouchers introduce a bulk `<form>` wrapping the entire table (R6). Nesting per-row `<form>` elements inside the bulk form would produce invalid HTML — the HTML spec forbids nested `<form>` tags and browser behavior is undefined. Instead, we use `formaction` on each button to override the form's submission target. The CSRF token hidden input from the outer form is automatically submitted with any button click. The `formaction` attribute is widely supported (HTML5) and already used by the bulk action buttons in R6.

### Eligibility Computation
The route handler computes a `voucher_actions` dict (keyed by code) at render time, similar to `grant_statuses` on the grants page. For each voucher:
```python
now = datetime.now(timezone.utc)
can_revoke = (
    voucher.status not in (VoucherStatus.REVOKED, VoucherStatus.EXPIRED)
    and now <= voucher.expires_utc
)
can_delete = voucher.redeemed_count == 0
```

### Alternatives Considered
1. **Single form wrapping entire table**: Rejected — conflicts with the bulk-operation form. Individual forms are isolated and simpler.
2. **JS-powered modal confirmation dialogs**: Rejected as primary mechanism — violates "forms must work without JS." Could be added as progressive enhancement later.

---

## R8: Audit Logging for Revoke and Delete Actions

### Decision
Extend the existing `AuditService` usage pattern to log revoke and delete actions:

- **Revoke**: `action="voucher.revoke"`, `target_type="voucher"`, `target_id=voucher.code`
- **Delete**: `action="voucher.delete"`, `target_type="voucher"`, `target_id=voucher.code`, `meta={"status_at_delete": voucher.status.value, "booking_ref": voucher.booking_ref}`. The service MUST capture these fields before issuing the hard delete, but MUST only call `audit_service.log_admin_action()` after the delete has been confirmed successful (or perform both within a single database transaction).
- **Bulk revoke**: One log entry per successfully revoked voucher (same as single revoke)
- **Bulk delete**: One log entry per successfully deleted voucher (same as single delete). For each voucher, fields needed for `meta` are captured pre-delete, and the audit log entry is written only if that voucher's delete actually succeeds.

### Rationale
FR-020 requires logging all revoke and delete actions with admin identity. The existing pattern in `vouchers_ui.py` (for create) and `grants_ui.py` (for extend/revoke) uses `audit_service.log_admin_action()`. Maintaining one log entry per voucher (not one per bulk operation) ensures granular traceability.

For delete actions, the meta field captures the voucher's state at deletion time because the record is hard-deleted afterward. To avoid recording a successful delete in the audit log when the database delete fails or is rejected (for example, due to a `redeemed_count` race), implementations MUST either:

- capture the required voucher fields before attempting the delete, perform the delete, and only then call `audit_service.log_admin_action()` if the delete succeeds; or
- wrap the delete and the audit log write in a single atomic transaction so that they either both commit or both roll back.

### Alternatives Considered
1. **Single bulk audit entry per operation**: Rejected — loses per-voucher traceability. If a bulk operation deletes 15 vouchers, there should be 15 audit entries so each can be investigated individually.
2. **Pre-delete snapshot in separate table**: Rejected — adds schema complexity. The meta field on the audit log entry is sufficient when combined with the post-delete (or transactional) logging pattern described above.
3. **Add specialized AuditService methods (log_voucher_revoked, log_voucher_deleted)**: Considered — may be added for consistency with `log_voucher_created()`, but `log_admin_action()` is sufficient and used by the existing route handlers.

---

## R9: Feedback Message Format for Bulk Operations

### Decision
Bulk operation feedback messages follow this format:
- **All succeeded**: `"Revoked 5 vouchers successfully"`
- **Partial success**: `"Revoked 3 vouchers, skipped 2 (1 expired, 1 already revoked)"`
- **All skipped**: `"No vouchers revoked — 3 skipped (2 expired, 1 already revoked)"`
- **None selected**: `"No vouchers selected"` (FR-016, as error)
- **Delete partial**: `"Deleted 2 vouchers, skipped 3 (already redeemed)"`

### Rationale
FR-015 requires a summary "indicating how many vouchers were affected and how many were skipped, with reasons." The message is built using `urllib.parse.quote_plus()` for proper URL encoding before being placed in the redirect query parameter (consistent with existing feedback pattern but ensuring punctuation and non-ASCII characters are handled safely). Skip reasons are grouped by category for clarity.

### Implementation
The bulk endpoint builds a `BulkResult` dataclass:
```python
@dataclass
class BulkResult:
    action: str  # "revoked" or "deleted"
    success_count: int
    skip_reasons: dict[str, int]  # e.g., {"expired": 2, "already revoked": 1}
```

The result is formatted into a single-line message string before URL-encoding into the redirect query parameter.

### Alternatives Considered
1. **JSON response with detailed per-voucher results**: Rejected — the UI uses PRG pattern with query-parameter flash messages, not JSON responses.
2. **Separate success/error messages**: Rejected — a single summary is clearer for partial-success scenarios where there is no clear "success" or "error."
