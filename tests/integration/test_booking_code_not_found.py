# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for booking code not found scenarios."""

import pytest
from sqlmodel import Session

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    BookingNotFoundError,
)


@pytest.mark.asyncio
class TestBookingCodeNotFound:
    """Test 404 responses when booking code not found."""

    async def test_code_not_in_events(self, db_session: Session) -> None:
        """Booking code does not match any event."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        validator = BookingCodeValidator(db_session)
        with pytest.raises(BookingNotFoundError, match="Booking not found"):
            await validator.validate_and_create_grant(code="NONEXISTENT", device_id="device1")

    async def test_no_events_cached(self, db_session: Session) -> None:
        """No events cached for integration."""
        config = HAIntegrationConfig(
            integration_id="rental1",
            auth_attribute="slot_code",
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()

        validator = BookingCodeValidator(db_session)
        with pytest.raises(BookingNotFoundError):
            await validator.validate_and_create_grant(code="1234", device_id="device1")
