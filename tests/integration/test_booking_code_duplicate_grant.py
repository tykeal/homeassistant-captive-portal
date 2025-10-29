# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for duplicate booking code grant."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    DuplicateGrantError,
)


@pytest.mark.asyncio
class TestBookingCodeDuplicateGrant:
    """Test 409 responses for duplicate active grants (idempotency)."""

    async def test_duplicate_grant_same_booking(self, db_session: Session) -> None:
        """Same booking code already has active grant."""
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
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=23),
            slot_code="1234",
            slot_name="Smith",
            last_four="5678",
        )
        db_session.add(event)
        db_session.commit()

        # Create first grant
        grant1 = AccessGrant(
            device_id="device1",
            booking_ref="1234",
            mac="00:00:00:00:00:00",
            integration_id="rental1",
            start_utc=event.start_utc,
            end_utc=event.end_utc,
        )
        db_session.add(grant1)
        db_session.commit()

        # Attempt to create second grant with same booking code
        validator = BookingCodeValidator(db_session)
        with pytest.raises(DuplicateGrantError, match="Active grant already exists"):
            await validator.validate_and_create_grant(code="1234", device_id="device2")

    async def test_expired_grant_allows_new(self, db_session: Session) -> None:
        """Expired grant does not prevent new grant."""
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
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=23),
            slot_code="1234",
            slot_name="Smith",
            last_four="5678",
        )
        db_session.add(event)
        db_session.commit()

        # Create expired grant
        old_grant = AccessGrant(
            device_id="device_old",
            booking_identifier="1234",
            integration_id="rental1",
            start_utc=now - timedelta(days=2),
            end_utc=now - timedelta(days=1),  # expired
        )
        db_session.add(old_grant)
        db_session.commit()

        # New grant should succeed
        validator = BookingCodeValidator(db_session)
        grant = await validator.validate_and_create_grant(code="1234", device_id="device_new")

        assert grant is not None
        assert grant.booking_identifier == "1234"
