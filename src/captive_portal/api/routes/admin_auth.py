# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""
Admin authentication routes (login, logout, bootstrap).

Implements:
- Admin login with session creation
- Admin logout with session destruction
- Bootstrap initial admin account (first-run only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.password_hashing import hash_password, verify_password
from captive_portal.security.session_middleware import SessionMiddleware

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response payload."""

    success: bool
    admin_id: UUID  # Changed from int to UUID
    username: str
    email: str
    csrf_token: str


class BootstrapRequest(BaseModel):
    """Bootstrap initial admin request."""

    username: str
    password: str
    email: EmailStr


class BootstrapResponse(BaseModel):
    """Bootstrap response."""

    success: bool
    message: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    db: Session = Depends(get_session),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> LoginResponse:
    """
    Admin login endpoint.

    Validates credentials and creates session cookie.
    """
    stmt = select(AdminUser).where(AdminUser.username == login_data.username)
    admin = db.exec(stmt).first()

    if not admin or not verify_password(login_data.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    session_middleware: SessionMiddleware = request.app.state.session_middleware
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    session_middleware.create_session(response, admin.id, ip_address, user_agent)

    csrf_token = csrf.generate_token()
    csrf.set_csrf_cookie(response, csrf_token)

    return LoginResponse(
        success=True,
        admin_id=admin.id,
        username=admin.username,
        email=admin.email,
        csrf_token=csrf_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> dict[str, str]:
    """
    Admin logout endpoint.

    Destroys session and clears cookies.
    """
    csrf.validate_token(request)

    session_id = request.state.session_id
    if session_id:
        session_middleware: SessionMiddleware = request.app.state.session_middleware
        session_middleware.delete_session(response, session_id)

    return {"message": "Logged out successfully"}


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_admin(
    bootstrap_req: BootstrapRequest,
    db: Session = Depends(get_session),
) -> BootstrapResponse:
    """
    Bootstrap initial admin account (first-run only).

    Creates the first admin user if no admins exist.
    Subsequent calls will be rejected.
    """
    stmt = select(AdminUser)
    existing_admins = db.exec(stmt).first()

    if existing_admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts already exist. Bootstrap is only allowed for initial setup.",
        )

    password_hash = hash_password(bootstrap_req.password)
    admin = AdminUser(
        username=bootstrap_req.username,
        password_hash=password_hash,
        email=bootstrap_req.email,
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return BootstrapResponse(
        success=True,
        message=f"Admin user '{admin.username}' created successfully",
    )


@router.get("/csrf-token")
async def get_csrf_token(
    request: Request,
    response: Response,
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> dict[str, str]:
    """
    Get or generate CSRF token for forms.

    Returns existing token from cookie or generates a new one.
    """
    existing_token = csrf.get_token_from_request(request)
    if existing_token:
        return {"csrf_token": existing_token}

    new_token = csrf.generate_token()
    csrf.set_csrf_cookie(response, new_token)
    return {"csrf_token": new_token}
