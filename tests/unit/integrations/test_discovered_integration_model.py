# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for DiscoveredIntegration and DiscoveryResult Pydantic models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from captive_portal.integrations.ha_discovery_service import (
    DiscoveredIntegration,
    DiscoveryResult,
)


# ---------------------------------------------------------------------------
# DiscoveredIntegration — field types & defaults
# ---------------------------------------------------------------------------


class TestDiscoveredIntegrationDefaults:
    """Verify field types, defaults, and required fields."""

    def test_minimal_construction(self) -> None:
        """DiscoveredIntegration should accept minimal required fields."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental Calendar",
            state="on",
        )
        assert item.entity_id == "calendar.rental"
        assert item.friendly_name == "Rental Calendar"
        assert item.state == "on"

    def test_already_configured_defaults_false(self) -> None:
        """already_configured should default to False."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="off",
        )
        assert item.already_configured is False

    def test_optional_fields_default_none(self) -> None:
        """event_summary, event_start, event_end should default to None."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="on",
        )
        assert item.event_summary is None
        assert item.event_start is None
        assert item.event_end is None

    def test_optional_fields_set(self) -> None:
        """Optional fields should accept string values."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="on",
            event_summary="Guest: Alice",
            event_start="2025-07-01T14:00:00",
            event_end="2025-07-05T10:00:00",
        )
        assert item.event_summary == "Guest: Alice"
        assert item.event_start == "2025-07-01T14:00:00"
        assert item.event_end == "2025-07-05T10:00:00"

    def test_missing_entity_id_raises(self) -> None:
        """entity_id is required; omitting it should raise ValidationError."""
        with pytest.raises(ValidationError):
            DiscoveredIntegration(
                friendly_name="Rental",
                state="on",
            )  # type: ignore[call-arg]

    def test_missing_friendly_name_raises(self) -> None:
        """friendly_name is required; omitting it should raise ValidationError."""
        with pytest.raises(ValidationError):
            DiscoveredIntegration(
                entity_id="calendar.rental",
                state="on",
            )  # type: ignore[call-arg]

    def test_missing_state_raises(self) -> None:
        """state is required; omitting it should raise ValidationError."""
        with pytest.raises(ValidationError):
            DiscoveredIntegration(
                entity_id="calendar.rental",
                friendly_name="Rental",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# state_display derivation
# ---------------------------------------------------------------------------


class TestStateDisplay:
    """Verify state_display is correctly derived from state."""

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("on", "Active booking"),
            ("off", "No active bookings"),
            ("unavailable", "Unavailable"),
        ],
    )
    def test_known_states(self, state: str, expected: str) -> None:
        """Known states should map to human-readable display strings."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state=state,
        )
        assert item.state_display == expected

    def test_unknown_state_passes_through(self) -> None:
        """Unknown state values should pass through as-is."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="idle",
        )
        assert item.state_display == "idle"


# ---------------------------------------------------------------------------
# JSON serialization round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    """Verify JSON serialization and deserialization."""

    def test_round_trip(self) -> None:
        """model_dump_json + model_validate_json should round-trip cleanly."""
        original = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental Calendar",
            state="on",
            event_summary="Guest: Alice",
            event_start="2025-07-01T14:00:00",
            event_end="2025-07-05T10:00:00",
            already_configured=True,
        )
        json_str = original.model_dump_json()
        restored = DiscoveredIntegration.model_validate_json(json_str)
        assert restored.entity_id == original.entity_id
        assert restored.friendly_name == original.friendly_name
        assert restored.state == original.state
        assert restored.state_display == original.state_display
        assert restored.event_summary == original.event_summary
        assert restored.event_start == original.event_start
        assert restored.event_end == original.event_end
        assert restored.already_configured == original.already_configured

    def test_state_display_in_json(self) -> None:
        """state_display should appear in JSON output."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="off",
        )
        data = json.loads(item.model_dump_json())
        assert "state_display" in data
        assert data["state_display"] == "No active bookings"


# ---------------------------------------------------------------------------
# DiscoveryResult wrapper
# ---------------------------------------------------------------------------


class TestDiscoveryResult:
    """Verify DiscoveryResult wrapper model."""

    def test_available_with_integrations(self) -> None:
        """available=True result should carry a list of integrations."""
        item = DiscoveredIntegration(
            entity_id="calendar.rental",
            friendly_name="Rental",
            state="on",
        )
        result = DiscoveryResult(available=True, integrations=[item])
        assert result.available is True
        assert len(result.integrations) == 1
        assert result.integrations[0].entity_id == "calendar.rental"
        assert result.error_message is None
        assert result.error_category is None

    def test_unavailable_with_error(self) -> None:
        """available=False result should carry error details."""
        result = DiscoveryResult(
            available=False,
            error_message="Connection refused",
            error_category="connection",
        )
        assert result.available is False
        assert result.error_message == "Connection refused"
        assert result.error_category == "connection"

    def test_unavailable_empty_integrations(self) -> None:
        """Unavailable result should have an empty integrations list."""
        result = DiscoveryResult(
            available=False,
            error_message="Timeout",
            error_category="timeout",
        )
        assert result.integrations == []

    def test_default_integrations_list(self) -> None:
        """integrations should default to an empty list."""
        result = DiscoveryResult(available=True)
        assert result.integrations == []
        assert result.error_message is None

    def test_available_required(self) -> None:
        """available field is required."""
        with pytest.raises(ValidationError):
            DiscoveryResult()  # type: ignore[call-arg]
