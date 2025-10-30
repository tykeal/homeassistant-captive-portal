# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Booking code validation service with case-insensitive matching."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, func, select

from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent


class BookingNotFoundError(Exception):
    """Booking code not found in any event."""

    pass


class BookingOutsideWindowError(Exception):
    """Booking is outside the active time window."""

    pass


class DuplicateGrantError(Exception):
    """Active grant already exists for this booking."""

    pass


class IntegrationUnavailableError(Exception):
    """Integration is not available or configured."""

    pass


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

        Storage and display: Values are stored and displayed in their original case
        as received from Home Assistant/Rental Control integration.

        Matching logic: Comparison is case-insensitive to improve guest experience
        (e.g., "ABC123", "abc123", and "AbC123" all match the same booking).

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
        statement: Any = (
            select(RentalControlEvent)
            .where(RentalControlEvent.integration_id == integration.integration_id)
            .where(func.lower(getattr(RentalControlEvent, attr_name)) == normalized_input.lower())
        )

        result: RentalControlEvent | None = self.session.exec(statement).first()
        return result

    @staticmethod
    def is_valid_slot_code(code: str) -> bool:
        r"""
        Validate slot_code format (^\d{4,}$).

        Args:
            code: The code to validate

        Returns:
            True if valid slot_code format, False otherwise
        """
        return bool(re.match(r"^\d{4,}$", code))

    @staticmethod
    def is_valid_last_four(code: str) -> bool:
        r"""
        Validate last_four format (^\d{4}$).

        Args:
            code: The code to validate

        Returns:
            True if valid last_four format, False otherwise
        """
        return bool(re.match(r"^\d{4}$", code))

    @staticmethod
    def is_valid_slot_name(name: str) -> bool:
        """
        Validate slot_name format (non-empty, trimmed, <=128 chars).

        Args:
            name: The slot name to validate

        Returns:
            True if valid slot_name format, False otherwise
        """
        if not name or not name.strip():
            return False
        trimmed = name.strip()
        return len(trimmed) <= 128

    @staticmethod
    def normalize_slot_name(name: str) -> str:
        """
        Normalize slot_name by trimming whitespace.

        Args:
            name: The slot name to normalize

        Returns:
            Trimmed slot name
        """
        return name.strip()

    async def validate_and_create_grant(self, code: str, device_id: str) -> AccessGrant:
        """
        Validate booking code and create access grant.

        Args:
            code: Booking code from guest
            device_id: Device identifier

        Returns:
            Created access grant

        Raises:
            IntegrationUnavailableError: No integration configured
            BookingNotFoundError: Booking not found
            BookingOutsideWindowError: Booking not in active window
            DuplicateGrantError: Active grant already exists
        """
        # Get first integration (for now, single integration support)
        integration: HAIntegrationConfig | None = self.session.exec(
            select(HAIntegrationConfig).limit(1)
        ).first()

        if not integration:
            raise IntegrationUnavailableError("No integration configured")

        # Find matching event
        event = self.validate_code(code, integration)

        if not event:
            raise BookingNotFoundError("Booking not found")

        # Check time window
        now = datetime.now(timezone.utc)
        grace_minutes = integration.checkout_grace_minutes

        # Ensure event times are timezone-aware for comparison
        start_utc = (
            event.start_utc
            if event.start_utc.tzinfo
            else event.start_utc.replace(tzinfo=timezone.utc)
        )
        end_utc = (
            event.end_utc if event.end_utc.tzinfo else event.end_utc.replace(tzinfo=timezone.utc)
        )

        # Allow early check-in up to 60 minutes before start (Phase 5: guests can arrive early)
        early_checkin_window = start_utc - timedelta(minutes=60)
        if now < early_checkin_window:
            raise BookingOutsideWindowError("Booking not yet active")

        # Check if after end + grace

        effective_end = end_utc + timedelta(minutes=grace_minutes)
        if now > effective_end:
            raise BookingOutsideWindowError("Booking expired")

        # Check for duplicate active grant
        existing: AccessGrant | None = self.session.exec(
            select(AccessGrant)
            .where(AccessGrant.booking_ref == code)
            .where(AccessGrant.end_utc > now)
        ).first()

        if existing:
            raise DuplicateGrantError("Active grant already exists")

        # Create new grant
        grant = AccessGrant(
            device_id=device_id,
            booking_ref=code,  # Use booking_ref field
            mac="00:00:00:00:00:00",  # Placeholder, will be updated by controller
            integration_id=integration.integration_id,
            start_utc=start_utc,
            end_utc=effective_end,
        )

        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)

        return grant
