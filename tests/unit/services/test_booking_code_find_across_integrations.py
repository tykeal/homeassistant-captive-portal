# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for BookingCodeValidator.find_across_integrations."""

from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlmodel import Session, create_engine

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.services.booking_code_validator import BookingCodeValidator


@pytest.fixture()
def test_db_session() -> Generator[Session, None, None]:
    """Create an in-memory test database session."""
    engine = create_engine("sqlite:///:memory:")
    from captive_portal.models import (
        HAIntegrationConfig,
        RentalControlEvent,
    )

    HAIntegrationConfig.metadata.create_all(engine)
    RentalControlEvent.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


class TestFindAcrossIntegrationsNoIntegrations:
    """Test find_across_integrations with zero integrations."""

    def test_returns_none_none_when_no_integrations(self, test_db_session: Session) -> None:
        """Return (None, None) when no integrations configured."""
        validator = BookingCodeValidator(test_db_session)
        event, integration = validator.find_across_integrations("ABC123")

        assert event is None
        assert integration is None


class TestFindAcrossIntegrationsSingleIntegration:
    """Test find_across_integrations with one integration."""

    def test_finds_code_in_single_integration(self, test_db_session: Session) -> None:
        """Find matching booking code in the only integration."""
        integration = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        test_db_session.add(integration)
        test_db_session.commit()

        event = RentalControlEvent(
            integration_id="calendar.rental_1",
            event_index=0,
            slot_code="ABC123",
            slot_name="Guest One",
            last_four="1234",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        test_db_session.add(event)
        test_db_session.commit()

        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("abc123")

        assert found_event is not None
        assert found_event.slot_code == "ABC123"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_1"

    def test_returns_none_when_code_not_in_single_integration(
        self, test_db_session: Session
    ) -> None:
        """Return (None, None) when code not found in only integration."""
        integration = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        test_db_session.add(integration)
        test_db_session.commit()

        event = RentalControlEvent(
            integration_id="calendar.rental_1",
            event_index=0,
            slot_code="ABC123",
            slot_name="Guest One",
            last_four="1234",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        test_db_session.add(event)
        test_db_session.commit()

        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("NONEXISTENT")

        assert found_event is None
        assert found_integration is None


class TestFindAcrossIntegrationsMultipleIntegrations:
    """Test find_across_integrations with two integrations."""

    @pytest.fixture()
    def two_integrations(
        self, test_db_session: Session
    ) -> tuple[HAIntegrationConfig, HAIntegrationConfig]:
        """Create two integrations with events in the test database."""
        integration_1 = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        integration_2 = HAIntegrationConfig(
            integration_id="calendar.rental_2",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=30,
        )
        test_db_session.add(integration_1)
        test_db_session.add(integration_2)
        test_db_session.commit()

        event_1 = RentalControlEvent(
            integration_id="calendar.rental_1",
            event_index=0,
            slot_code="FIRST111",
            slot_name="Guest First",
            last_four="1111",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        event_2 = RentalControlEvent(
            integration_id="calendar.rental_2",
            event_index=0,
            slot_code="SECOND222",
            slot_name="Guest Second",
            last_four="2222",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        test_db_session.add(event_1)
        test_db_session.add(event_2)
        test_db_session.commit()

        return integration_1, integration_2

    def test_finds_code_in_first_integration(
        self,
        test_db_session: Session,
        two_integrations: tuple[HAIntegrationConfig, HAIntegrationConfig],
    ) -> None:
        """Find code that belongs to the first integration."""
        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("first111")

        assert found_event is not None
        assert found_event.slot_code == "FIRST111"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_1"

    def test_finds_code_in_second_integration(
        self,
        test_db_session: Session,
        two_integrations: tuple[HAIntegrationConfig, HAIntegrationConfig],
    ) -> None:
        """Find code that belongs to the second integration."""
        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("second222")

        assert found_event is not None
        assert found_event.slot_code == "SECOND222"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_2"

    def test_returns_none_when_code_not_in_any_integration(
        self,
        test_db_session: Session,
        two_integrations: tuple[HAIntegrationConfig, HAIntegrationConfig],
    ) -> None:
        """Return (None, None) when code not in any integration."""
        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("MISSING999")

        assert found_event is None
        assert found_integration is None

    def test_case_insensitive_across_integrations(
        self,
        test_db_session: Session,
        two_integrations: tuple[HAIntegrationConfig, HAIntegrationConfig],
    ) -> None:
        """Case-insensitive lookup works across integrations."""
        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("SeCOnD222")

        assert found_event is not None
        assert found_event.slot_code == "SECOND222"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_2"

    def test_whitespace_trimmed_across_integrations(
        self,
        test_db_session: Session,
        two_integrations: tuple[HAIntegrationConfig, HAIntegrationConfig],
    ) -> None:
        """Whitespace is trimmed before lookup."""
        validator = BookingCodeValidator(test_db_session)
        found_event, found_integration = validator.find_across_integrations("  second222  ")

        assert found_event is not None
        assert found_event.slot_code == "SECOND222"


class TestFindAcrossIntegrationsDifferentAttrs:
    """Test find_across_integrations with different identifier attrs."""

    def test_different_identifier_attrs_per_integration(self, test_db_session: Session) -> None:
        """Each integration uses its own identifier_attr for lookup."""
        integration_1 = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        integration_2 = HAIntegrationConfig(
            integration_id="calendar.rental_2",
            identifier_attr=IdentifierAttr.SLOT_NAME,
            checkout_grace_minutes=15,
        )
        test_db_session.add(integration_1)
        test_db_session.add(integration_2)
        test_db_session.commit()

        event_1 = RentalControlEvent(
            integration_id="calendar.rental_1",
            event_index=0,
            slot_code="CODE111",
            slot_name="Name One",
            last_four="1111",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        event_2 = RentalControlEvent(
            integration_id="calendar.rental_2",
            event_index=0,
            slot_code="CODE222",
            slot_name="Name Two",
            last_four="2222",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime.now(timezone.utc),
            raw_attributes="{}",
        )
        test_db_session.add(event_1)
        test_db_session.add(event_2)
        test_db_session.commit()

        validator = BookingCodeValidator(test_db_session)

        # Search by slot_name should find event in integration_2
        found_event, found_integration = validator.find_across_integrations("name two")
        assert found_event is not None
        assert found_event.slot_name == "Name Two"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_2"

        # Search by slot_code should find event in integration_1
        found_event, found_integration = validator.find_across_integrations("code111")
        assert found_event is not None
        assert found_event.slot_code == "CODE111"
        assert found_integration is not None
        assert found_integration.integration_id == "calendar.rental_1"
