# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for BookingCodeValidator.find_across_integrations."""

from datetime import datetime, timedelta, timezone
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

    def test_prefers_active_match_across_integrations(
        self,
        test_db_session: Session,
    ) -> None:
        """Pick the globally best match when the same code exists in multiple integrations."""
        expired_integration = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        active_integration = HAIntegrationConfig(
            integration_id="calendar.rental_2",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        test_db_session.add(expired_integration)
        test_db_session.add(active_integration)
        test_db_session.commit()

        now = datetime.now(timezone.utc)
        expired_event = RentalControlEvent(
            integration_id=expired_integration.integration_id,
            event_index=0,
            slot_code="6709",
            slot_name="Expired Guest",
            last_four="6709",
            start_utc=now - timedelta(days=2),
            end_utc=now - timedelta(hours=2),
            raw_attributes="{}",
        )
        active_event = RentalControlEvent(
            integration_id=active_integration.integration_id,
            event_index=0,
            slot_code="6709",
            slot_name="Current Guest",
            last_four="6709",
            start_utc=now - timedelta(minutes=30),
            end_utc=now + timedelta(hours=2),
            raw_attributes="{}",
        )
        test_db_session.add(expired_event)
        test_db_session.add(active_event)
        test_db_session.commit()

        validator = BookingCodeValidator(test_db_session)

        found_event, found_integration = validator.find_across_integrations("6709")

        assert found_event is not None
        assert found_event.slot_name == "Current Guest"
        assert found_event.integration_id == active_integration.integration_id
        assert found_integration is not None
        assert found_integration.integration_id == active_integration.integration_id

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

    def test_prefers_active_event_when_code_reused(
        self,
        test_db_session: Session,
    ) -> None:
        """Return the active event when expired and active bookings share a code."""
        integration = HAIntegrationConfig(
            integration_id="calendar.rental_1",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        test_db_session.add(integration)
        test_db_session.commit()

        now = datetime.now(timezone.utc)
        expired_event = RentalControlEvent(
            integration_id=integration.integration_id,
            event_index=0,
            slot_code="6709",
            slot_name="Expired Guest",
            last_four="6709",
            start_utc=now - timedelta(days=2),
            end_utc=now - timedelta(hours=2),
            raw_attributes="{}",
        )
        active_event = RentalControlEvent(
            integration_id=integration.integration_id,
            event_index=1,
            slot_code="6709",
            slot_name="Current Guest",
            last_four="6709",
            start_utc=now - timedelta(minutes=30),
            end_utc=now + timedelta(hours=2),
            raw_attributes="{}",
        )
        test_db_session.add(expired_event)
        test_db_session.add(active_event)
        test_db_session.commit()

        validator = BookingCodeValidator(test_db_session)

        found_event, found_integration = validator.find_across_integrations("6709")

        assert found_event is not None
        assert found_event.event_index == active_event.event_index
        assert found_event.slot_name == "Current Guest"
        assert found_integration is not None
        assert found_integration.integration_id == integration.integration_id


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


class TestFindAcrossIntegrationsVlanSelection:
    """Test VLAN-aware candidate selection across colliding booking codes."""

    @staticmethod
    def _add_integration(
        session: Session,
        integration_id: str,
        allowed_vlans: list[int] | None,
    ) -> None:
        """Persist an integration with a VLAN allowlist."""
        session.add(
            HAIntegrationConfig(
                integration_id=integration_id,
                identifier_attr=IdentifierAttr.SLOT_CODE,
                checkout_grace_minutes=15,
                allowed_vlans=allowed_vlans,
            )
        )
        session.commit()

    @staticmethod
    def _add_event(
        session: Session,
        integration_id: str,
        code: str,
        start_offset_minutes: int,
    ) -> None:
        """Persist an active booking event starting at a relative offset."""
        now = datetime.now(timezone.utc)
        session.add(
            RentalControlEvent(
                integration_id=integration_id,
                event_index=0,
                slot_code=code,
                slot_name=f"Guest {integration_id}",
                last_four="1234",
                start_utc=now + timedelta(minutes=start_offset_minutes),
                end_utc=now + timedelta(days=1),
                raw_attributes="{}",
            )
        )
        session.commit()

    def test_colliding_code_resolves_to_device_vlan(self, test_db_session: Session) -> None:
        """A colliding code resolves to the integration matching the device VLAN."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        # The VLAN 61 booking starts later, so it wins the time-based
        # preference ordering and would be selected without VLAN filtering.
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert integration.integration_id == "calendar.vlan_63"
        assert event is not None

    def test_colliding_code_resolves_for_other_vlan(self, test_db_session: Session) -> None:
        """The same collision resolves the other way for a VLAN 61 device."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="61")

        assert integration is not None
        assert integration.integration_id == "calendar.vlan_61"

    def test_returns_candidate_when_no_vlan_matches(self, test_db_session: Session) -> None:
        """Return a candidate so the caller can report a VLAN denial."""
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        event, integration = validator.find_across_integrations("5773", device_vid="63")

        # Distinguishable from an unknown code, which yields (None, None).
        assert event is not None
        assert integration is not None
        assert integration.integration_id == "calendar.vlan_61"

    def test_unknown_code_still_returns_none(self, test_db_session: Session) -> None:
        """An unknown code returns (None, None) regardless of VLAN."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        event, integration = validator.find_across_integrations("0000", device_vid="63")

        assert event is None
        assert integration is None

    def test_unrestricted_integration_matches_any_vlan(self, test_db_session: Session) -> None:
        """An integration without an allowlist remains reachable."""
        self._add_integration(test_db_session, "calendar.open", None)
        self._add_event(test_db_session, "calendar.open", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert integration.integration_id == "calendar.open"

    def test_matching_vlan_preferred_over_newer_mismatch(self, test_db_session: Session) -> None:
        """A VLAN-matching integration wins over a non-matching newer booking."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -1)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert integration.integration_id == "calendar.vlan_63"

    def test_missing_vid_falls_back_to_candidate(self, test_db_session: Session) -> None:
        """A device with no VID still yields a candidate for denial reporting."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        event, integration = validator.find_across_integrations("5773", device_vid=None)

        assert event is not None
        assert integration is not None

    def test_ambiguous_match_logs_warning(
        self, test_db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Multiple integrations valid for one VLAN emit a warning."""
        self._add_integration(test_db_session, "calendar.first", [63])
        self._add_integration(test_db_session, "calendar.second", [63])
        self._add_event(test_db_session, "calendar.first", "5773", -120)
        self._add_event(test_db_session, "calendar.second", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        with caplog.at_level("WARNING", logger="captive_portal.guest"):
            _event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert "matches 2 integrations" in caplog.text

    def test_backward_compatible_without_vid(self, test_db_session: Session) -> None:
        """Omitting device_vid preserves the previous selection behaviour."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773")

        # Time-based ordering still selects the most recently started event.
        assert integration is not None
        assert integration.integration_id == "calendar.vlan_61"

    def test_correct_vlan_wins_over_active_wrong_vlan(self, test_db_session: Session) -> None:
        """A non-active correct-VLAN booking beats an active wrong-VLAN one."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        # VLAN 63 booking is expired; VLAN 61 booking is active. Without
        # VLAN filtering the active booking wins on tier alone.
        now = datetime.now(timezone.utc)
        test_db_session.add(
            RentalControlEvent(
                integration_id="calendar.vlan_63",
                event_index=0,
                slot_code="5773",
                slot_name="Expired Guest",
                last_four="1234",
                start_utc=now - timedelta(days=5),
                end_utc=now - timedelta(days=4),
                raw_attributes="{}",
            )
        )
        test_db_session.commit()
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="63")

        # Selecting the VLAN 63 booking lets the caller report an accurate
        # booking-window error instead of a misleading network error.
        assert integration is not None
        assert integration.integration_id == "calendar.vlan_63"

    def test_future_correct_vlan_wins_over_active_wrong_vlan(
        self, test_db_session: Session
    ) -> None:
        """A future correct-VLAN booking beats an active wrong-VLAN one."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", 60 * 24 * 3)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert integration.integration_id == "calendar.vlan_63"

    def test_mixed_allowlists_unchanged_without_vid(self, test_db_session: Session) -> None:
        """An unknown VLAN must not reorder mixed restricted/open candidates."""
        self._add_integration(test_db_session, "calendar.restricted", [61])
        self._add_integration(test_db_session, "calendar.open", None)
        # The restricted booking starts later, so time ordering prefers it.
        self._add_event(test_db_session, "calendar.open", "5773", -120)
        self._add_event(test_db_session, "calendar.restricted", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid=None)

        # Filtering on an unknown VID would drop the restricted candidate
        # and wrongly promote the open one, turning a denial into a grant.
        assert integration is not None
        assert integration.integration_id == "calendar.restricted"

    def test_mixed_allowlists_filtered_with_vid(self, test_db_session: Session) -> None:
        """A known VLAN still selects the reachable integration."""
        self._add_integration(test_db_session, "calendar.restricted", [61])
        self._add_integration(test_db_session, "calendar.open", None)
        self._add_event(test_db_session, "calendar.open", "5773", -120)
        self._add_event(test_db_session, "calendar.restricted", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid="63")

        assert integration is not None
        assert integration.integration_id == "calendar.open"

    @pytest.mark.parametrize("bad_vid", ["", "   ", "abc", "0", "4095", "-1", "63.5"])
    def test_unusable_vid_does_not_reorder_candidates(
        self, test_db_session: Session, bad_vid: str
    ) -> None:
        """Unparseable VIDs must not promote an unrestricted booking."""
        self._add_integration(test_db_session, "calendar.restricted", [61])
        self._add_integration(test_db_session, "calendar.open", None)
        self._add_event(test_db_session, "calendar.open", "5773", -120)
        self._add_event(test_db_session, "calendar.restricted", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        _event, integration = validator.find_across_integrations("5773", device_vid=bad_vid)

        # Filtering on an unusable VID would drop the restricted candidate
        # and wrongly promote the open one, turning a denial into a grant.
        assert integration is not None
        assert integration.integration_id == "calendar.restricted"

    def test_unusable_vid_logs_ambiguity(
        self, test_db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Falling back on an unusable VID still reports ambiguity."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        with caplog.at_level("WARNING", logger="captive_portal.guest"):
            validator.find_across_integrations("5773", device_vid="abc")

        assert "matches 2 integrations" in caplog.text

    def test_no_vlan_match_logs_ambiguity(
        self, test_db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Falling back when no candidate qualifies reports ambiguity."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        with caplog.at_level("WARNING", logger="captive_portal.guest"):
            validator.find_across_integrations("5773", device_vid="99")

        assert "matches 2 integrations" in caplog.text

    def test_single_vlan_match_logs_nothing(
        self, test_db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unambiguous VLAN-filtered match emits no warning."""
        self._add_integration(test_db_session, "calendar.vlan_63", [63])
        self._add_integration(test_db_session, "calendar.vlan_61", [61])
        self._add_event(test_db_session, "calendar.vlan_63", "5773", -120)
        self._add_event(test_db_session, "calendar.vlan_61", "5773", -10)

        validator = BookingCodeValidator(test_db_session)
        with caplog.at_level("WARNING", logger="captive_portal.guest"):
            validator.find_across_integrations("5773", device_vid="63")

        assert "matches" not in caplog.text
