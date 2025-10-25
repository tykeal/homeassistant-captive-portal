# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Voucher model for captive portal access codes."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import field_validator, computed_field
from sqlmodel import Field, SQLModel


class VoucherStatus(str, Enum):
    """Voucher lifecycle status."""

    UNUSED = "unused"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Voucher(SQLModel, table=True):
    """Voucher represents a redeemable access code.

    Attributes:
        code: Unique voucher code (A-Z0-9, 4-24 chars) - Primary Key
        created_utc: Creation timestamp (UTC)
        duration_minutes: Grant duration in minutes
        up_kbps: Upload bandwidth limit (nullable, >0 when set)
        down_kbps: Download bandwidth limit (nullable, >0 when set)
        status: Current voucher status
        booking_ref: Optional case-sensitive booking reference
        redeemed_count: Number of times redeemed
        last_redeemed_utc: Timestamp of last redemption (nullable)
    """

    code: str = Field(primary_key=True, max_length=24, min_length=4)
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_minutes: int = Field(gt=0)
    up_kbps: Optional[int] = Field(default=None, gt=0)
    down_kbps: Optional[int] = Field(default=None, gt=0)
    status: VoucherStatus = Field(default=VoucherStatus.UNUSED)
    booking_ref: Optional[str] = Field(default=None, max_length=128)
    redeemed_count: int = Field(default=0, ge=0)
    last_redeemed_utc: Optional[datetime] = Field(default=None)

    @field_validator("code")
    @classmethod
    def validate_code_charset(cls, v: str) -> str:
        """Validate voucher code contains only A-Z and 0-9."""
        if not v.isupper() or not v.isalnum():
            raise ValueError("Voucher code must contain only A-Z and 0-9")
        return v

    @field_validator("booking_ref")
    @classmethod
    def validate_booking_ref(cls, v: Optional[str]) -> Optional[str]:
        """Trim whitespace from booking reference while preserving case."""
        return v.strip() if v else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expires_utc(self) -> datetime:
        """Computed expiration timestamp (created + duration, floored to minute)."""
        expiry = self.created_utc + timedelta(minutes=self.duration_minutes)
        # Floor to minute precision
        return expiry.replace(second=0, microsecond=0)
