# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Rental Control event cache model."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class RentalControlEvent(SQLModel, table=True):
    """Cached Rental Control event data for voucher creation.

    Attributes:
        id: Primary key
        integration_id: FK to HAIntegrationConfig
        event_index: Event position from sensor (0-N)
        slot_name: Guest name identifier (optional)
        slot_code: Numeric booking code (optional, 4+ digits)
        last_four: Last 4 digits identifier (optional, exactly 4 digits)
        start_utc: Booking start timestamp
        end_utc: Booking end timestamp
        raw_attributes: JSON blob of full event attributes
        created_utc: Record creation timestamp
        updated_utc: Record last update timestamp
    """

    __tablename__ = "rental_control_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    integration_id: UUID = Field(foreign_key="ha_integration_config.id", index=True)
    event_index: int = Field(ge=0)
    slot_name: Optional[str] = Field(default=None, max_length=255)
    slot_code: Optional[str] = Field(default=None, max_length=255)  # regex ^\\d{4,}$
    last_four: Optional[str] = Field(default=None, max_length=4)  # regex ^\\d{4}$
    start_utc: datetime
    end_utc: datetime
    raw_attributes: str  # JSON blob
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
