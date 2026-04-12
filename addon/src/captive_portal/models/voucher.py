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
        activated_utc: Timestamp when expiry timer started (nullable).
            For pre-existing vouchers upgraded via migration, this
            may be an approximation derived from ``created_utc``
            rather than the actual first redemption time.
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
    activated_utc: Optional[datetime] = Field(default=None)

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
        """Computed expiration timestamp (activation or creation + duration).

        When the voucher has been activated, expiration is calculated from
        ``activated_utc``; otherwise it falls back to ``created_utc`` as
        an estimate for display before first use.  The result is floored
        to minute precision.

        Note: Ensures timezone awareness even if stored timestamps are
        naive (from DB).
        """
        base = self.activated_utc if self.activated_utc is not None else self.created_utc
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)

        expiry = base + timedelta(minutes=self.duration_minutes)
        # Floor to minute precision
        return expiry.replace(second=0, microsecond=0)

    @property
    def is_activated_for_expiry(self) -> bool:
        """Whether the voucher's expiry timer has started.

        Returns True when the voucher has been activated (via
        ``activated_utc``), has been redeemed at least once, or
        has moved beyond UNUSED status.  Legacy upgraded rows may
        lack ``activated_utc`` even after redemption, so the
        fallback checks ensure correct expiration enforcement.
        """
        return (
            self.activated_utc is not None
            or self.redeemed_count > 0
            or self.status != VoucherStatus.UNUSED
        )
