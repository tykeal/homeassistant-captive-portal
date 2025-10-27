# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin API routes for access grant management."""

from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.database import get_session
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.grant_service import (
    GrantNotFoundError,
    GrantOperationError,
    GrantService,
)

router = APIRouter(prefix="/api/grants", tags=["grants"])


class GrantListResponse(BaseModel):
    """Response model for grant listing."""

    id: UUID
    voucher_code: str | None
    booking_ref: str | None
    mac: str
    start_utc: datetime
    end_utc: datetime
    status: GrantStatus
    created_utc: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class ExtendGrantRequest(BaseModel):
    """Request model for extending grant duration."""

    additional_minutes: int = Field(gt=0, le=10080, description="Minutes to add (max 7 days)")


class GrantExtendResponse(BaseModel):
    """Response model for grant extension."""

    id: UUID
    end_utc: datetime
    status: GrantStatus


class RevokeGrantResponse(BaseModel):
    """Response model for grant revocation."""

    id: UUID
    status: GrantStatus


@router.get("/", response_model=List[GrantListResponse])
async def list_grants(
    status_filter: GrantStatus | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> List[AccessGrant]:
    """List access grants (admin only).

    Args:
        status_filter: Optional status filter (PENDING, ACTIVE, EXPIRED, REVOKED)
        limit: Max results (default 100, max 1000)
        session: Database session
        admin_id: Authenticated admin user ID

    Returns:
        List of access grants
    """
    limit = min(limit, 1000)

    from sqlmodel import desc

    statement = select(AccessGrant).order_by(desc(AccessGrant.created_utc)).limit(limit)

    if status_filter:
        statement = statement.where(AccessGrant.status == status_filter)

    grants = list(session.exec(statement).all())

    # Audit log
    audit_service = AuditService(session)
    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="list_grants",
        target_type="access_grant",
        metadata={
            "status_filter": status_filter.value if status_filter else None,
            "count": len(grants),
        },
    )

    return grants


@router.post("/{grant_id}/extend", response_model=GrantExtendResponse)
async def extend_grant(
    grant_id: UUID,
    request: ExtendGrantRequest,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> AccessGrant:
    """Extend grant duration (admin only).

    Args:
        grant_id: Grant UUID
        request: Extension parameters
        session: Database session
        admin_id: Authenticated admin user ID

    Returns:
        Updated grant

    Raises:
        404: Grant not found
        409: Grant cannot be extended (revoked)
    """
    grant_service = GrantService(session)
    audit_service = AuditService(session)

    try:
        grant = await grant_service.extend(
            grant_id=grant_id,
            additional_minutes=request.additional_minutes,
            current_time=datetime.now(timezone.utc),
        )

        await audit_service.log_admin_action(
            admin_id=admin_id,
            action="extend_grant",
            target_type="access_grant",
            target_id=str(grant_id),
            metadata={
                "additional_minutes": request.additional_minutes,
                "new_end_utc": grant.end_utc.isoformat(),
            },
        )

        return grant

    except GrantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except GrantOperationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{grant_id}/revoke", response_model=RevokeGrantResponse)
async def revoke_grant(
    grant_id: UUID,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> AccessGrant:
    """Revoke access grant (admin only).

    Args:
        grant_id: Grant UUID
        session: Database session
        admin_id: Authenticated admin user ID

    Returns:
        Revoked grant

    Raises:
        404: Grant not found
    """
    grant_service = GrantService(session)
    audit_service = AuditService(session)

    try:
        grant = await grant_service.revoke(
            grant_id=grant_id,
            current_time=datetime.now(timezone.utc),
        )

        await audit_service.log_admin_action(
            admin_id=admin_id,
            action="revoke_grant",
            target_type="access_grant",
            target_id=str(grant_id),
        )

        return grant

    except GrantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
