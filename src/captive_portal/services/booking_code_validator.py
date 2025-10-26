# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Booking code validation service with case-insensitive matching."""

from typing import Optional

from sqlmodel import Session, func, select

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent


class BookingCodeValidator:
    """Service for validating guest booking codes against rental control events.

    Implements D10: Case-insensitive matching, case-sensitive storage/display.

    Attributes:
        session: Database session for queries
    """

    def __init__(self, session: Session) -> None:
        """Initialize validator with database session.

        Args:
            session: SQLModel database session
        """
        self.session = session

    def validate_code(
        self, user_input: str, integration: HAIntegrationConfig
    ) -> Optional[RentalControlEvent]:
        """Validate booking code against rental control events.

        Performs case-insensitive lookup using the configured auth attribute.
        Trims whitespace from input. Returns event with original case preserved.

        Args:
            user_input: Guest-provided booking code (any case)
            integration: Integration config specifying auth attribute

        Returns:
            RentalControlEvent with original case if found, None otherwise
        """
        # Normalize input: trim whitespace
        normalized_input = user_input.strip()

        # Get the configured attribute name
        attr_name = integration.identifier_attr.value

        # Build case-insensitive query
        # LOWER(field) = LOWER(input)
        statement = (
            select(RentalControlEvent)
            .where(RentalControlEvent.integration_id == integration.id)
            .where(func.lower(getattr(RentalControlEvent, attr_name)) == normalized_input.lower())
        )

        result = self.session.exec(statement).first()
        return result
