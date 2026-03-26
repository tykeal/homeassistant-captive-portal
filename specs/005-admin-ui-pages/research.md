SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Admin UI Pages

**Feature**: 005-admin-ui-pages | **Date**: 2025-07-16

## R1: Logout Route Architecture — `/admin/logout` vs `/api/admin/auth/logout`

### Decision
Create a dedicated `/admin/logout` HTML route (`admin_logout_ui.py`) that internally calls the existing session store to destroy the session, then issues a `303 See Other` redirect to `/admin/login`. This route is CSRF-exempt per FR-019.

### Rationale
The existing logout endpoint at `/api/admin/auth/logout` returns a JSON response (`{"message": "Logged out successfully"}`). This works for API consumers but fails for browser-based HTML form submissions — the user sees raw JSON instead of being redirected to the login page. The spec requires (FR-019) that the nav bar logout form submits a POST to `/admin/logout`, not directly to the API.

The HTML logout handler will:
1. Read `session_id` from `request.state` (set by `SessionMiddleware`)
2. Call `session_store.delete(session_id)` to destroy the session
3. Delete the session cookie via `response.delete_cookie()`
4. Redirect to `{root_path}/admin/login` with HTTP 303

This is safe to implement without CSRF because logout is idempotent and cannot be exploited for state changes beyond ending the user's own session.

### Alternatives Considered
1. **Modify `/api/admin/auth/logout` to detect Accept header and return redirect for browsers**: Rejected — mixes API and UI concerns; breaks API contract for existing callers.
2. **Client-side JS redirect after API call**: Rejected — violates FR-010 (forms must work without JS) and FR-019 (must be an HTML form POST).
3. **Redirect from API endpoint itself**: Rejected — would break the documented JSON API contract and any programmatic callers.

### Impact on Existing Templates
All existing templates (`dashboard.html`, `grants_enhanced.html`, `portal_settings.html`, `integrations.html`) currently have the logout form posting to `{{ rp }}/api/admin/logout`. This path does **not** exist today (the only existing JSON logout endpoint is `/api/admin/auth/logout`), so the templates are incorrect and must be updated to post to `{{ rp }}/admin/logout` instead.

---

## R2: Cache-Control Headers for Admin Pages (FR-028)

### Decision
Add cache-control headers to all `/admin/*` responses in the `SecurityHeadersMiddleware` by checking the request path. Admin responses will include:
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```

### Rationale
FR-028 and User Story 4 (SC-3) require that after logout, the browser's back button does not display cached admin content. Without these headers, browsers may cache HTML responses and display them from the bfcache (back-forward cache) even after the session is destroyed.

### Alternatives Considered
1. **Per-route header setting in each UI handler**: Rejected — duplicates code across every handler, easy to forget on new pages, and violates DRY.
2. **Separate middleware class**: Rejected — adds unnecessary complexity when the existing `SecurityHeadersMiddleware` already processes all responses and can easily add a path check.
3. **Set headers in template via meta tags**: Rejected — `<meta http-equiv>` is less reliable than HTTP headers and some browsers ignore it for caching decisions.

### Implementation
In `SecurityHeadersMiddleware.dispatch()`, add a path check:
```python
if request.url.path.startswith("/admin"):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
```

---

## R3: Voucher List Data Access — No `GET /api/vouchers` Endpoint

### Decision
Query vouchers directly in the `vouchers_ui.py` route handler via SQLModel, consistent with how `integrations_ui.py` queries `HAIntegrationConfig` and `portal_settings_ui.py` queries `PortalConfig`. Do not create a separate `GET /api/vouchers` API endpoint for this feature.

### Rationale
The spec assumption explicitly states: "The existing backend API for vouchers currently only implements `POST /api/vouchers` (create). This spec assumes that additional voucher endpoints … will be added to support the required UI behavior, or that the UI requirements will be updated to match whatever voucher APIs are actually provided."

The existing pattern in this project is that UI routes (`*_ui.py`) query the database directly using `Session = Depends(get_session)` and pass results to Jinja2 templates. The API routes (`/api/*`) serve JSON for programmatic callers. Adding a JSON list endpoint would be scope creep and is not required by any spec requirement.

The UI route will:
1. Query `select(Voucher).order_by(desc(Voucher.created_utc)).limit(500)`
2. Compute derived redemption status per FR-018: `"Unredeemed"` when `redeemed_count == 0`, `"Redeemed"` when `redeemed_count > 0`
3. Pass results to the template

### Alternatives Considered
1. **Create `GET /api/vouchers` endpoint and have UI call it via fetch/JS**: Rejected — adds API surface area outside spec scope, and JS-based data loading conflicts with the "forms must work without JS" principle.
2. **Create `GET /api/vouchers` and have the UI route call it internally**: Rejected — unnecessary indirection; the UI route already has database access via dependency injection.

---

## R4: Dashboard Statistics & Activity Feed Data Source

### Decision
Create a `DashboardService` class in `services/dashboard_service.py` that aggregates statistics and recent activity using direct SQL queries against existing tables. The service will compute:
- **Active grants count**: `SELECT COUNT(*) FROM accessgrant WHERE status != 'revoked' AND start_utc <= now AND end_utc > now`
- **Pending grants count**: `SELECT COUNT(*) FROM accessgrant WHERE status != 'revoked' AND start_utc > now`
- **Available vouchers count**: `SELECT COUNT(*) FROM voucher WHERE status = 'unused' AND (created_utc + INTERVAL '1 minute' * duration_minutes) > now` (expiry is computed in SQL from `created_utc` and `duration_minutes`; `Voucher.expires_utc` is a Pydantic computed property, not a DB column)
- **Integrations count**: `SELECT COUNT(*) FROM haintegrationconfig`
- **Recent activity**: `SELECT * FROM auditlog ORDER BY timestamp_utc DESC LIMIT 20`

### Rationale
The dashboard requires aggregated statistics (FR-002) and a recent activity feed (FR-003) from data that already exists in the database. The `AuditLog` table records all admin actions with timestamp, action type, target, and actor — exactly what the activity feed needs. Grant and voucher counts come from their respective tables.

A dedicated service class follows the existing pattern (`GrantService`, `VoucherService`, `AuditService`) and keeps the route handler thin.

### Alternatives Considered
1. **Inline queries in the route handler**: Rejected — violates the project's service-layer pattern and makes unit testing harder.
2. **Use existing repository classes**: Partially used — the repositories don't have aggregate count methods, so the service will use direct SQLModel `select()` with `func.count()` for efficiency rather than loading all entities.
3. **Cache dashboard stats in memory**: Rejected — premature optimization; with 1–5 concurrent admins and small data volumes, real-time queries are sufficient.

### Activity Feed Data Mapping
The `AuditLog` model fields map to the dashboard template columns as follows:
| Template Column | AuditLog Field | Notes |
|----------------|----------------|-------|
| Time | `timestamp_utc` | Format: `%Y-%m-%d %H:%M` |
| Action | `action` | e.g., `grant.revoke`, `voucher.create` |
| Target | `target_type` + `target_id` | Combined display |
| Admin | `actor` | Username or admin UUID |

The existing `dashboard.html` template references `log.timestamp`, `log.action`, `log.target_type`, `log.target_id`, and `log.admin_username`. The service will need to resolve `actor` (which stores UUID or username) to a display name. Since audit log actors are stored as `str(admin_id)` by `log_admin_action()`, the service will join with `AdminUser` to get usernames, or fall back to the raw actor string for system/guest actions.

---

## R5: Grant Page Form Actions — UI Routes for Extend/Revoke

### Decision
Create dedicated POST endpoints in `grants_ui.py`:
- `POST /admin/grants/extend/{grant_id}` — accepts form fields `csrf_token` and `minutes`, calls `GrantService.extend()`, redirects back to grants page with success/error feedback via query parameters.
- `POST /admin/grants/revoke/{grant_id}` — accepts form field `csrf_token`, calls `GrantService.revoke()`, redirects back to grants page with feedback.

### Rationale
The existing `grants_enhanced.html` template already has inline forms posting to `{{ rp }}/admin/grants/extend/{{ grant.id }}` and `{{ rp }}/admin/grants/revoke/{{ grant.id }}`. These are HTML form submissions (method="POST"), which is exactly what FR-010 requires. However, no route handlers exist for these paths yet.

The UI routes will follow the Post/Redirect/Get (PRG) pattern used by `portal_settings_ui.py` — process the form submission, perform the action, and redirect with a success or error message in query parameters. This prevents form resubmission on browser refresh.

### Alternatives Considered
1. **POST directly to `/api/grants/{id}/extend`**: Rejected — API returns JSON, not a redirect. Browser would display raw JSON.
2. **JS-based fetch to API with client-side redirect**: Rejected — violates FR-010 (must work without JS).
3. **Reuse existing API route with content negotiation**: Rejected — overcomplicates the API route and mixes concerns.

### Error Handling
| Scenario | User Feedback |
|----------|--------------|
| Extend revoked grant | Error: "Cannot extend a revoked grant" (from `GrantOperationError`) |
| Extend expired grant | Success: grant reactivated (per `GrantService.extend()` behavior) |
| Revoke already-revoked grant | Success: idempotent (per `GrantService.revoke()` behavior) |
| Grant not found | Error: "Grant not found" (from `GrantNotFoundError`) |
| Invalid minutes value | Error: "Minutes must be between 1 and 1440" |

---

## R6: Voucher Creation Form — HTML POST with CSRF

### Decision
The voucher creation form in `vouchers.html` will submit a POST to `/admin/vouchers/create` with form fields:
- `csrf_token` (hidden)
- `duration_minutes` (number input, required, min=1, max=43200)
- `booking_ref` (text input, optional, max=128)

The route handler in `vouchers_ui.py` will call `VoucherService.create()` and redirect back to the vouchers page. On success, the newly created voucher code will be displayed prominently (FR-017) via a query parameter `new_code=ABC123` that triggers a highlighted display section in the template.

### Rationale
This follows the PRG pattern established by the integrations and settings pages. The CSRF protection uses the existing double-submit cookie pattern — the token is embedded as a hidden form field and validated via `csrf.validate_token(request)`.

### Alternatives Considered
1. **Modal dialog with JS for creation**: Rejected — would not work without JS (FR-015 requires form POST as primary mechanism).
2. **Separate page for voucher creation**: Rejected — adds unnecessary navigation; the integrations page already demonstrates inline creation forms effectively.
3. **Display new code on a confirmation page**: Rejected — adds a separate route/template; query parameter approach is simpler and follows the established feedback pattern.

---

## R7: Template Consistency — Nav Bar Logout Form Update

### Decision
Update all existing admin templates to change the logout form action from `{{ rp }}/api/admin/logout` to `{{ rp }}/admin/logout`. The form should NOT include a CSRF token (FR-019 explicitly states logout is CSRF-exempt).

### Rationale
Currently, all four existing admin templates (`dashboard.html`, `grants_enhanced.html`, `portal_settings.html`, `integrations.html`) post the logout form to the JSON API endpoint. Per FR-019, the logout form must post to `/admin/logout` which handles session destruction and browser redirect. The CSRF hidden input in the logout form can be removed since FR-019 explicitly makes logout CSRF-exempt.

### Templates to Update
1. `admin/dashboard.html` — change logout action, remove CSRF input
2. `admin/grants_enhanced.html` — change logout action, remove CSRF input
3. `admin/portal_settings.html` — change logout action, remove CSRF input
4. `admin/integrations.html` — change logout action, remove CSRF input
5. `admin/vouchers.html` — new template, will use correct action from the start

---

## R8: Ingress Root Path Handling (FR-024)

### Decision
Follow the exact same pattern as all existing templates: `{% set rp = request.scope.root_path %}` at the top of each template, and prefix all URLs with `{{ rp }}`.

### Rationale
Every existing admin template uses this pattern. The FastAPI `request.scope.root_path` is automatically set by ASGI servers (Uvicorn) based on the `--root-path` flag or the `X-Forwarded-Prefix` header that HA ingress sets. This is a proven, working pattern in the project.

No changes needed to the routing or middleware — just consistent use of `{{ rp }}` in new templates.

---

## R9: Empty State and Error Handling Patterns

### Decision
All list pages (Grants, Vouchers, Dashboard activity) will handle empty states gracefully:
- **Grants page**: When no grants match the filter, display "No grants found" in a styled empty-state row or message (FR-005, edge case).
- **Vouchers page**: When no vouchers exist, display "No vouchers found. Create one above." (acceptance scenario 5).
- **Dashboard**: When counts are zero, display `0` (not blank or error). When activity feed is empty, display "No recent activity" (FR-004).
- **API errors**: If a database query fails, catch the exception and display an inline error message rather than a 500 page (edge case: "backend API unreachable").

### Rationale
FR-004 and the acceptance scenarios explicitly require graceful empty-state handling. The existing templates do not have empty-state handling — the `{% for %}` loops simply render nothing when the list is empty, leaving a table with only headers. Adding `{% if not items %}` blocks with clear messaging improves UX per constitution principle III.

### Implementation Pattern
```jinja2
{% if grants %}
  {% for grant in grants %}
    <tr>...</tr>
  {% endfor %}
{% else %}
  <tr>
    <td colspan="9" class="empty-state">No grants found for the selected filter.</td>
  </tr>
{% endif %}
```

---

## R10: Status Computation for Grants and Vouchers

### Decision
Grant status is computed at query time in the UI route handler, matching the existing pattern in `grants.py` API route. Voucher redemption status is derived per FR-018.

### Rationale
The `AccessGrant.status` field in the database may be stale (e.g., a grant's `end_utc` has passed but `status` still says `"active"`). The existing `grants.py` API route already re-computes status based on current time:
- `current_time < start_utc` → PENDING
- `current_time >= end_utc` → EXPIRED
- otherwise → ACTIVE
- `status == REVOKED` → preserved as-is

The UI route will apply the same logic. For vouchers, the spec (FR-018) requires a derived redemption status: "Unredeemed" when `redeemed_count == 0`, "Redeemed" when `redeemed_count > 0`. The raw `VoucherStatus` (unused, active, expired, revoked) will also be displayed alongside.
