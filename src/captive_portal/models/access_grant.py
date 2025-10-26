# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Access grant model for active network authorizations."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class GrantStatus(str, Enum):
    """Access grant lifecycle status."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AccessGrant(SQLModel, table=True):
    """AccessGrant represents an active or historical network authorization.

    Attributes:
        id: Primary key (UUID)
        voucher_code: Optional FK to voucher (nullable)
        booking_ref: Optional case-sensitive booking identifier (nullable)
        mac: Device MAC address (required)
        session_token: Temporary session token fallback (nullable)
        start_utc: Grant start timestamp (UTC, minute precision)
        end_utc: Grant expiration timestamp (UTC, minute precision)
        controller_grant_id: External controller grant ID (nullable)
        status: Current grant status
        created_utc: Creation timestamp (UTC)
        updated_utc: Last update timestamp (UTC)
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    voucher_code: Optional[str] = Field(default=None, max_length=24, foreign_key="voucher.code")
    booking_ref: Optional[str] = Field(default=None, max_length=128)
    mac: str = Field(max_length=17, index=True)  # AA:BB:CC:DD:EE:FF format
    session_token: Optional[str] = Field(default=None, max_length=64)
    start_utc: datetime = Field(index=True)
    end_utc: datetime = Field(index=True)
    controller_grant_id: Optional[str] = Field(default=None, max_length=128)
    status: GrantStatus = Field(default=GrantStatus.PENDING)
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data: Any) -> None:
        """Initialize AccessGrant with minute-precision timestamp rounding."""
        # Round start_utc down to minute
        if "start_utc" in data:
            data["start_utc"] = data["start_utc"].replace(second=0, microsecond=0)
        # Round end_utc up to next minute (ceil)
        if "end_utc" in data:
            end = data["end_utc"]
            if end.second > 0 or end.microsecond > 0:
                from datetime import timedelta

                end = end.replace(second=0, microsecond=0) + timedelta(minutes=1)
            data["end_utc"] = end
        super().__init__(**data)
