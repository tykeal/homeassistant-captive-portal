# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for booking code case-insensitive validation (D10)."""

from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlmodel import Session, create_engine

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.models.rental_control_event import RentalControlEvent


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


@pytest.fixture
def sample_integration(test_db_session: Session) -> HAIntegrationConfig:
    """Create a sample integration configuration."""
    integration = HAIntegrationConfig(
        integration_id="test_rental_1",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=15,
    )
    test_db_session.add(integration)
    test_db_session.commit()
    test_db_session.refresh(integration)
    return integration


@pytest.fixture
def sample_event(
    test_db_session: Session, sample_integration: HAIntegrationConfig
) -> RentalControlEvent:
    """Create a sample rental control event with mixed case slot_code."""
    event = RentalControlEvent(
        integration_id=sample_integration.id,
        event_index=0,
        slot_code="ABC123",  # Mixed case
        slot_name="John Doe",
        last_four="1234",
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime.now(timezone.utc),
        raw_attributes="{}",
    )
    test_db_session.add(event)
    test_db_session.commit()
    test_db_session.refresh(event)
    return event


def test_booking_code_case_insensitive_match_lowercase(
    test_db_session: Session,
    sample_integration: HAIntegrationConfig,
    sample_event: RentalControlEvent,
) -> None:
    """Test booking code matches with lowercase input."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    validator = BookingCodeValidator(test_db_session)
    result = validator.validate_code("abc123", sample_integration)

    assert result is not None
    assert result.id == sample_event.id
    assert result.slot_code == "ABC123"  # Original case preserved


def test_booking_code_case_insensitive_match_uppercase(
    test_db_session: Session,
    sample_integration: HAIntegrationConfig,
    sample_event: RentalControlEvent,
) -> None:
    """Test booking code matches with uppercase input."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    validator = BookingCodeValidator(test_db_session)
    result = validator.validate_code("ABC123", sample_integration)

    assert result is not None
    assert result.id == sample_event.id
    assert result.slot_code == "ABC123"


def test_booking_code_case_insensitive_match_mixed(
    test_db_session: Session,
    sample_integration: HAIntegrationConfig,
    sample_event: RentalControlEvent,
) -> None:
    """Test booking code matches with different mixed case input."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    validator = BookingCodeValidator(test_db_session)
    result = validator.validate_code("aBc123", sample_integration)

    assert result is not None
    assert result.id == sample_event.id
    assert result.slot_code == "ABC123"


def test_booking_code_whitespace_trimmed(
    test_db_session: Session,
    sample_integration: HAIntegrationConfig,
    sample_event: RentalControlEvent,
) -> None:
    """Test booking code input is trimmed of whitespace."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    validator = BookingCodeValidator(test_db_session)
    result = validator.validate_code("  abc123  ", sample_integration)

    assert result is not None
    assert result.slot_code == "ABC123"


def test_booking_code_no_match_returns_none(
    test_db_session: Session,
    sample_integration: HAIntegrationConfig,
    sample_event: RentalControlEvent,
) -> None:
    """Test non-matching booking code returns None."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    validator = BookingCodeValidator(test_db_session)
    result = validator.validate_code("XYZ999", sample_integration)

    assert result is None


def test_booking_code_respects_identifier_attr_slot_name(
    test_db_session: Session, sample_event: RentalControlEvent
) -> None:
    """Test validator uses configured identifier attribute (slot_name)."""
    from captive_portal.services.booking_code_validator import BookingCodeValidator

    # Create integration configured for slot_name
    integration = HAIntegrationConfig(
        integration_id="test_rental_2",
        identifier_attr=IdentifierAttr.SLOT_NAME,
        checkout_grace_minutes=15,
    )
    test_db_session.add(integration)
    test_db_session.commit()

    # Create event with different slot_name case
    event = RentalControlEvent(
        integration_id=integration.id,
        event_index=0,
        slot_code="999999",
        slot_name="Jane Smith",  # Mixed case
        last_four="5678",
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime.now(timezone.utc),
        raw_attributes="{}",
    )
    test_db_session.add(event)
    test_db_session.commit()

    validator = BookingCodeValidator(test_db_session)

    # Should match slot_name, not slot_code
    result = validator.validate_code("jane smith", integration)
    assert result is not None
    assert result.slot_name == "Jane Smith"  # Original case

    # Should NOT match slot_code since we're using slot_name
    result = validator.validate_code("999999", integration)
    assert result is None
