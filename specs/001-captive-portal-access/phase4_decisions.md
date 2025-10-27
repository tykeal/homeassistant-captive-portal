<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Phase 4 Decisions: Admin Web Interface & Theming

**Date**: 2025-10-27T00:45:00Z
**Phase**: Phase 4 - Admin Web Interface & Theming
**Status**: ✅ DECISIONS APPROVED

---

## Overview

Phase 4 implements the admin web interface with authentication, session management, CSRF protection, and UI for managing grants, vouchers, and HA integrations. This document records all decisions made to enable Phase 4 implementation.

---

## Decisions Approved

### D12: Admin Authentication Method ✅ APPROVED
**Context**: Phase 4 implements admin login/session management

**Decision**: Option (a) Session cookies (HTTP-only, secure, SameSite=Strict)

**Rationale**:
- More secure (HTTP-only prevents XSS)
- Easier revocation (server-side session store)
- Aligns with traditional web app patterns
- Simpler implementation than OAuth2

**Implementation**:
- Session store: In-memory dict (future: Redis/DB)
- Session lifetime: Configurable (default 30 min idle, max 8 hours absolute)
- Rotation: On privilege escalation
- CSRF protection: Double-submit cookie pattern

**Files**: `src/captive_portal/security/session_middleware.py`

---

### D13: Password Hashing Algorithm ✅ APPROVED
**Context**: AdminAccount.password_hash needs secure hashing

**Decision**: Option (b) argon2 (modern, memory-hard, OWASP recommended)

**Rationale**:
- Memory-hard (resistant to GPU/ASIC attacks)
- OWASP recommended for new applications
- Tunable parameters (memory, parallelism, iterations)
- Better than bcrypt for future-proofing

**Implementation**:
- Library: `argon2-cffi`
- Params: Default OWASP (m=65536, t=3, p=4)
- Hash format: PHC string format
- Verification: Constant-time comparison

**File**: `src/captive_portal/security/password_hashing.py`

---

### D14: CSRF Token Strategy ✅ APPROVED
**Context**: Admin forms need CSRF protection

**Decision**: Option (a) Double-submit cookie (stateless, cookie + form field)

**Rationale**:
- Stateless (no session storage overhead)
- Works with session cookies
- Industry standard (Django, Rails)
- Simpler than synchronizer token

**Implementation**:
- Token: 32-byte random (base64-encoded)
- Cookie: `csrftoken` (SameSite=Strict, Secure)
- Form field: `<input type="hidden" name="csrf_token">`
- Validation: Compare cookie == form field (constant-time)

**File**: `src/captive_portal/security/csrf.py`

---

### D15: Admin UI Theme/Framework ✅ APPROVED
**Context**: Phase 4 adds admin templates

**Decision**: Option (a) Minimal CSS (no framework, custom styles)

**Rationale**:
- Smaller bundle size (addon bandwidth constraints)
- Faster load times
- No framework lock-in
- Sufficient for admin-only UI (not public-facing)

**Implementation**:
- Base styles: Modern CSS (grid, flexbox, CSS variables)
- Theme variables: Configurable colors, fonts
- Responsive: Mobile-friendly (viewport meta)
- Accessibility: Semantic HTML, ARIA labels

**File**: `src/captive_portal/web/themes/default/admin.css`

---

### D16: Guest Portal Theme Customization ✅ APPROVED
**Context**: Phase 5 adds guest-facing portal

**Decision**: Option (b) CSS variable overrides (admin-configurable colors)

**Rationale**:
- Balances simplicity and flexibility
- Admin can match property branding (colors, logo)
- No template complexity
- Sufficient for MVP

**Implementation**:
- Variables: `--primary-color`, `--logo-url`, `--background`
- Config: Admin UI form (color pickers)
- Storage: Database (GuestPortalTheme model)
- Injection: Dynamic `<style>` tag with variables

**Files**:
- `src/captive_portal/models/guest_portal_theme.py`
- `src/captive_portal/web/themes/default/guest.css`

---

### D17: Admin Session Lifetime ✅ APPROVED
**Context**: Session timeout for security vs. convenience

**Decision**: Option (b) Medium (30 min idle, 8 hr absolute)

**Rationale**:
- Balances security and admin convenience
- Idle timeout prevents abandoned sessions
- Absolute timeout forces re-auth daily
- Configurable via environment variable

**Implementation**:
- Idle timeout: Reset on activity (default 30 min)
- Absolute timeout: Max session age (default 8 hr)
- Config: `SESSION_IDLE_MINUTES=30`, `SESSION_MAX_HOURS=8`
- Enforcement: Middleware checks both timeouts

**File**: `src/captive_portal/security/session_middleware.py`

---

## Database Schema Changes Required

### Phase 4 Additions

#### AdminSession Model
```python
class AdminSession(SQLModel, table=True):
    """Server-side session storage."""
    id: str = Field(primary_key=True)  # Session ID (UUID)
    admin_id: int = Field(foreign_key="admin_account.id")
    created_utc: datetime
    last_activity_utc: datetime
    expires_utc: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
```

#### GuestPortalTheme Model
```python
class GuestPortalTheme(SQLModel, table=True):
    """Customizable guest portal theme."""
    id: Optional[int] = Field(default=None, primary_key=True)
    primary_color: str = Field(default="#007bff")  # Hex color
    logo_url: Optional[str]  # Path to uploaded logo
    background_color: str = Field(default="#ffffff")
    text_color: str = Field(default="#333333")
    created_utc: datetime
    updated_utc: datetime
```

---

## Implementation Scope

Phase 4 will deliver:
1. **Security Infrastructure**: Session management, CSRF protection, argon2 password hashing
2. **Admin Authentication**: Login/logout, session middleware, bootstrap admin creation
3. **Admin UI Routes**: Grants list/extend/revoke, voucher redemption, entity mapping CRUD
4. **Admin Templates**: Dashboard, grants management, minimal CSS theme
5. **Phase 3 UI Deferred**: HA integration config forms, guest booking code form, enhanced grants display
6. **Database Migrations**: AdminSession and GuestPortalTheme tables

---

**Approver**: User (tykeal@bardicgrove.org)
**Date**: 2025-10-27T00:45:00Z
**Status**: ✅ ALL DECISIONS APPROVED - READY FOR PHASE 4 IMPLEMENTATION
