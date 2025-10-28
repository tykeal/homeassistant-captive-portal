# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""
Admin account management routes.

Implements:
- List all admin accounts
- Create additional admin accounts
- Update admin account details
- Delete admin accounts
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.password_hashing import hash_password

router = APIRouter(prefix="/api/admin/accounts", tags=["admin-accounts"])


class AdminAccountCreate(BaseModel):
    """Request to create a new admin account."""

    username: str
    password: str
    email: EmailStr
    role: str = "admin"


class AdminAccountUpdate(BaseModel):
    """Request to update admin account details."""

    email: EmailStr | None = None
    password: str | None = None


class AdminAccountResponse(BaseModel):
    """Admin account response (without password hash)."""

    id: UUID
    username: str
    email: str
    role: str


def get_current_admin(request: Request, db: Session = Depends(get_session)) -> AdminUser:
    """
    Get currently authenticated admin from session.

    Raises HTTP 401 if not authenticated.
    """
    if not hasattr(request.state, "admin_id") or not request.state.admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    stmt = select(AdminUser).where(AdminUser.id == request.state.admin_id)
    admin = db.exec(stmt).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    return admin


@router.get("", response_model=list[AdminAccountResponse])
async def list_admin_accounts(
    request: Request,
    db: Session = Depends(get_session),
    _current_admin: AdminUser = Depends(get_current_admin),
) -> list[AdminAccountResponse]:
    """
    List all admin accounts.

    Requires authentication.
    """
    stmt = select(AdminUser)
    admins = db.exec(stmt).all()

    return [
        AdminAccountResponse(
            id=admin.id,
            username=admin.username,
            email=admin.email,
            role=admin.role,
        )
        for admin in admins
    ]


@router.post("", response_model=AdminAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_account(
    request: Request,
    account: AdminAccountCreate,
    _current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_session),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> AdminAccountResponse:
    """
    Create a new admin account.

    Requires authentication and valid CSRF token.
    """
    await csrf.validate_token(request)

    # Check for duplicate username
    stmt = select(AdminUser).where(AdminUser.username == account.username)
    existing_username = db.exec(stmt).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    # Check for duplicate email
    stmt = select(AdminUser).where(AdminUser.email == account.email)
    existing_email = db.exec(stmt).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    password_hash = hash_password(account.password)
    new_admin = AdminUser(
        username=account.username,
        password_hash=password_hash,
        email=account.email,
        role=account.role,
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return AdminAccountResponse(
        id=new_admin.id,
        username=new_admin.username,
        email=new_admin.email,
        role=new_admin.role,
    )


@router.patch("/{admin_id}", response_model=AdminAccountResponse)
async def update_admin_account(
    request: Request,
    admin_id: UUID,
    updates: AdminAccountUpdate,
    _current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_session),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> AdminAccountResponse:
    """
    Update an admin account.

    Requires authentication and valid CSRF token.
    """
    await csrf.validate_token(request)

    stmt = select(AdminUser).where(AdminUser.id == admin_id)
    admin = db.exec(stmt).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin account not found",
        )

    if updates.email is not None:
        # Check for duplicate email
        stmt = select(AdminUser).where(AdminUser.email == updates.email, AdminUser.id != admin_id)
        existing_email = db.exec(stmt).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )
        admin.email = updates.email

    if updates.password is not None:
        admin.password_hash = hash_password(updates.password)

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return AdminAccountResponse(
        id=admin.id,
        username=admin.username,
        email=admin.email,
        role=admin.role,
    )


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_account(
    request: Request,
    admin_id: UUID,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_session),
    csrf: CSRFProtection = Depends(get_csrf_protection),
) -> None:
    """
    Delete an admin account.

    Cannot delete own account. Requires authentication and valid CSRF token.
    """
    await csrf.validate_token(request)

    if current_admin.id == admin_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete your own account",
        )

    stmt = select(AdminUser).where(AdminUser.id == admin_id)
    admin = db.exec(stmt).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin account not found",
        )

    db.delete(admin)
    db.commit()
