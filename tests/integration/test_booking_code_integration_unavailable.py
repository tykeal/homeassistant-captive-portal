# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for booking code when integration unavailable."""

import pytest
from sqlmodel import Session

from captive_portal.services.booking_code_validator import (
    BookingCodeValidator,
    IntegrationUnavailableError,
)


@pytest.mark.asyncio
class TestBookingCodeIntegrationUnavailable:
    """Test deny-by-default when HA integration unavailable."""

    async def test_no_integration_config(self, db_session: Session) -> None:
        """No integration configuration exists."""
        validator = BookingCodeValidator(db_session)
        with pytest.raises(
            IntegrationUnavailableError,
            match="No integration configured",
        ):
            await validator.validate_and_create_grant(code="1234", device_id="device1")

    async def test_integration_disabled(self, db_session: Session) -> None:
        """Integration exists but is disabled."""
        # This test will be relevant when we add enabled/disabled flag
        # For now, just document the expectation
        pass
