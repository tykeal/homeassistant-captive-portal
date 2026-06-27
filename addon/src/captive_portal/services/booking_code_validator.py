# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Booking code validation service with case-insensitive matching."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

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
        return self._find_preferred_event(normalized_input, integration)

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

    def find_across_integrations(
        self, user_input: str
    ) -> tuple[RentalControlEvent, HAIntegrationConfig] | tuple[None, None]:
        """Search all integrations for a matching booking code.

        Iterates through all configured integrations and checks each one
        for a matching event using case-insensitive lookup.

        Args:
            user_input: Guest-provided booking code (any case)

        Returns:
            Tuple of (event, integration) if found, (None, None)
            otherwise.
        """
        normalized_input = user_input.strip()

        integrations: list[HAIntegrationConfig] = list(
            self.session.exec(select(HAIntegrationConfig)).all()
        )

        now = datetime.now(timezone.utc)
        candidates: list[tuple[RentalControlEvent, HAIntegrationConfig]] = []

        for integration in integrations:
            matches = self._find_matching_events(normalized_input, integration)
            candidates.extend((event, integration) for event in matches)

        if not candidates:
            return None, None

        result, integration = min(
            candidates,
            key=lambda candidate: self._event_preference_key(
                candidate[0],
                grace_minutes=candidate[1].checkout_grace_minutes,
                now=now,
            ),
        )
        return result, integration

    def _find_matching_events(
        self,
        normalized_input: str,
        integration: HAIntegrationConfig,
    ) -> list[RentalControlEvent]:
        """Find all matching events for a booking code within one integration.

        Args:
            normalized_input: Trimmed guest-provided booking code
            integration: Integration config specifying auth attribute and grace

        Returns:
            Matching events ordered by ``start_utc`` descending
        """
        attr_name = integration.identifier_attr.value
        statement: Any = (
            select(RentalControlEvent)
            .where(RentalControlEvent.integration_id == integration.integration_id)
            .where(func.lower(getattr(RentalControlEvent, attr_name)) == normalized_input.lower())
            .order_by(cast(Any, RentalControlEvent.start_utc).desc())
        )
        return list(self.session.exec(statement).all())

    def _find_preferred_event(
        self,
        normalized_input: str,
        integration: HAIntegrationConfig,
    ) -> RentalControlEvent | None:
        """Find the best-matching event for a booking code.

        Prefers events that are currently within the access window, then the
        nearest future booking, and finally the most recent matching event.

        Args:
            normalized_input: Trimmed guest-provided booking code
            integration: Integration config specifying auth attribute and grace

        Returns:
            Preferred matching event, or None when no event matches
        """
        matches = self._find_matching_events(normalized_input, integration)
        return self._select_preferred_event(
            matches,
            grace_minutes=integration.checkout_grace_minutes,
        )

    @staticmethod
    def _select_preferred_event(
        events: list[RentalControlEvent],
        *,
        grace_minutes: int,
        now: datetime | None = None,
    ) -> RentalControlEvent | None:
        """Choose the most relevant event from ordered matches.

        Args:
            events: Matching events ordered by ``start_utc`` descending
            grace_minutes: Checkout grace period for the integration
            now: Optional comparison timestamp for deterministic selection

        Returns:
            Active event when present, otherwise the nearest future event,
            otherwise the most recent expired match, or None if no events exist
        """
        if not events:
            return None

        comparison_time = now or datetime.now(timezone.utc)
        return min(
            events,
            key=lambda event: BookingCodeValidator._event_preference_key(
                event,
                grace_minutes=grace_minutes,
                now=comparison_time,
            ),
        )

    @staticmethod
    def _event_preference_key(
        event: RentalControlEvent,
        *,
        grace_minutes: int,
        now: datetime,
    ) -> tuple[int, float]:
        """Build a sortable preference key for matching events.

        Args:
            event: Matching event candidate
            grace_minutes: Checkout grace period for the integration
            now: Comparison timestamp

        Returns:
            Tuple ordering active events first, then nearest future events,
            then the most recent expired event
        """
        start_utc = BookingCodeValidator._ensure_timezone_aware(event.start_utc)
        end_utc = BookingCodeValidator._ensure_timezone_aware(event.end_utc)
        early_checkin_window = start_utc - timedelta(minutes=60)
        effective_end = end_utc + timedelta(minutes=grace_minutes)
        start_timestamp = start_utc.timestamp()

        if early_checkin_window <= now <= effective_end:
            return 0, -start_timestamp
        if now < early_checkin_window:
            return 1, start_timestamp
        return 2, -start_timestamp

    @staticmethod
    def _ensure_timezone_aware(value: datetime) -> datetime:
        """Return a timezone-aware UTC datetime for comparisons.

        Args:
            value: Datetime read from persistence

        Returns:
            Timezone-aware datetime in UTC
        """
        if not value.tzinfo:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

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
        # Check if any integrations exist
        all_integrations: list[HAIntegrationConfig] = list(
            self.session.exec(select(HAIntegrationConfig)).all()
        )
        if not all_integrations:
            raise IntegrationUnavailableError("No integration configured")

        # Search all integrations for matching event
        event, integration = self.find_across_integrations(code)

        if not event or not integration:
            raise BookingNotFoundError("Booking not found")

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

        existing: AccessGrant | None = self.session.exec(
            select(AccessGrant)
            .where(AccessGrant.booking_ref == code)
            .where(AccessGrant.end_utc > now)
        ).first()

        if existing:
            raise DuplicateGrantError("Active grant already exists")

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
