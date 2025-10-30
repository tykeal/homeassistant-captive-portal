# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for booking code lookup happy path."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import BookingCodeValidator


@pytest.mark.asyncio
class TestBookingCodeLookupHappyPath:
    """Test booking code validation happy path (event 0 & 1, time window)."""

    async def test_lookup_event_0_current_booking(self, db_session: Session) -> None:
        """Event 0 is current booking (start <= now < end)."""
        # Setup integration config
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        # Create current event (event_0)
        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now - timedelta(hours=2),
            end_utc=now + timedelta(hours=2),
            slot_code="1234",
            slot_name="Smith",
            last_four="5678",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        # Validate booking code
        validator = BookingCodeValidator(db_session)
        grant = await validator.validate_and_create_grant(code="1234", device_id="device1")

        assert grant is not None
        assert grant.booking_identifier == "1234"
        assert grant.integration_id == "rental1"

    async def test_lookup_event_1_upcoming_booking(self, db_session: Session) -> None:
        """Event 1 is upcoming booking (start today or future)."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        # Create upcoming event (event_1)
        now = datetime.now(timezone.utc)
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=1,
            start_utc=now + timedelta(hours=1),
            end_utc=now + timedelta(days=1),
            slot_code="5678",
            slot_name="Doe",
            last_four="1234",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        # Validate booking code
        validator = BookingCodeValidator(db_session)
        grant = await validator.validate_and_create_grant(code="5678", device_id="device2")

        assert grant is not None
        assert grant.booking_identifier == "5678"

    async def test_time_window_validation(self, db_session: Session) -> None:
        """Access allowed from start to end + grace_period."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=30,
        )
        db_session.add(config)
        db_session.commit()

        now = datetime.now(timezone.utc)
        # Event ending soon, but within grace period
        event = RentalControlEvent(
            integration_id="rental1",
            event_index=0,
            start_utc=now - timedelta(hours=24),
            end_utc=now + timedelta(minutes=15),  # ends in 15 min
            slot_code="9999",
            slot_name="Grace",
            last_four="0000",
            raw_attributes="{}",
        )
        db_session.add(event)
        db_session.commit()

        validator = BookingCodeValidator(db_session)
        grant = await validator.validate_and_create_grant(code="9999", device_id="device3")

        assert grant is not None
        # Grant end should be event.end_utc + grace_period
        expected_end = event.end_utc + timedelta(minutes=30)
        assert grant.end_utc <= expected_end + timedelta(seconds=60)  # tolerance
