# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Admin API routes for voucher management."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from captive_portal.models.voucher import Voucher
from captive_portal.persistence.database import get_session
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_service import (
    VoucherCollisionError,
    VoucherService,
)

router = APIRouter(prefix="/api/vouchers", tags=["vouchers"])


class CreateVoucherRequest(BaseModel):
    """Request model for creating vouchers."""

    duration_minutes: int = Field(gt=0, le=43200, description="Duration in minutes (max 30 days)")
    booking_ref: str | None = Field(default=None, max_length=128)
    up_kbps: int | None = Field(default=None, gt=0)
    down_kbps: int | None = Field(default=None, gt=0)
    code_length: int = Field(default=10, ge=4, le=24)
    allowed_vlans: list[int] | None = Field(default=None)

    @field_validator("allowed_vlans", mode="before")
    @classmethod
    def validate_vlans(cls, v: list[int] | None) -> list[int] | None:
        """Validate VLAN IDs are integers in the 1-4094 range."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("allowed_vlans must be a list")
        for vid in v:
            if isinstance(vid, bool) or not isinstance(vid, int) or vid < 1 or vid > 4094:
                raise ValueError(f"Invalid VLAN ID: {vid} (must be 1-4094)")
        return sorted(set(v))


class VoucherResponse(BaseModel):
    """Response model for voucher operations."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    duration_minutes: int
    booking_ref: str | None
    up_kbps: int | None
    down_kbps: int | None
    status: str
    created_utc: datetime
    allowed_vlans: list[int] | None = None


@router.post("/", response_model=VoucherResponse, status_code=status.HTTP_201_CREATED)
async def create_voucher(
    request: CreateVoucherRequest,
    session: Session = Depends(get_session),
    admin_id: UUID = Depends(require_admin),
) -> Voucher:
    """Create new voucher (admin only).

    Args:
        request: Voucher creation parameters
        session: Database session
        admin_id: Authenticated admin user ID

    Returns:
        Created voucher

    Raises:
        409: Voucher code collision (retry exhausted)
        400: Invalid parameters
    """
    voucher_service = VoucherService(session)
    audit_service = AuditService(session)

    try:
        voucher = await voucher_service.create(
            duration_minutes=request.duration_minutes,
            booking_ref=request.booking_ref,
            up_kbps=request.up_kbps,
            down_kbps=request.down_kbps,
            code_length=request.code_length,
            allowed_vlans=request.allowed_vlans,
        )

        await audit_service.log_admin_action(
            admin_id=admin_id,
            action="create_voucher",
            target_type="voucher",
            target_id=voucher.code,
            metadata={
                "duration_minutes": request.duration_minutes,
                "booking_ref": request.booking_ref,
            },
        )

        return voucher

    except VoucherCollisionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
