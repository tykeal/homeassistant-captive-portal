# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for booking code outside time window."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    BookingOutsideWindowError,
)


@pytest.mark.asyncio
class TestBookingCodeOutsideWindow:
    """Test 410 responses for bookings outside active window."""

    async def test_before_start_time(self, db_session: Session) -> None:
        """Booking not yet started."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now + timedelta(hours=2),  # starts in 2 hours
            end_utc=now + timedelta(days=1),
            slot_code="1234",
            slot_name="Future",
            last_four="5678",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        validator = BookingCodeValidator(db_session)
        with pytest.raises(BookingOutsideWindowError, match="Booking not yet active"):
            await validator.validate_and_create_grant(code="1234", device_id="device1")

    async def test_after_end_plus_grace(self, db_session: Session) -> None:
        """Booking ended and grace period expired."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now - timedelta(days=2),
            end_utc=now - timedelta(hours=1),  # ended 1 hour ago (> 15min grace)
            slot_code="1234",
            slot_name="Expired",
            last_four="5678",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        validator = BookingCodeValidator(db_session)
        with pytest.raises(BookingOutsideWindowError, match="Booking expired"):
            await validator.validate_and_create_grant(code="1234", device_id="device1")
