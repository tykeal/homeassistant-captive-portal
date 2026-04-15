# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HADiscoveryService.discover() (T008)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session


def _make_entity(
    entity_id: str,
    state: str = "off",
    friendly_name: str = "Test",
    message: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Build a fake HA entity state dict."""
    attrs: dict[str, Any] = {"friendly_name": friendly_name}
    if message is not None:
        attrs["message"] = message
    if start_time is not None:
        attrs["start_time"] = start_time
    if end_time is not None:
        attrs["end_time"] = end_time
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attrs,
    }


def _make_registry_entry(
    entity_id: str,
    platform: str = "rental_control",
) -> dict[str, Any]:
    """Build a fake HA entity registry entry."""
    return {"entity_id": entity_id, "platform": platform}


@pytest.mark.asyncio
async def test_discover_filters_rental_control_entities(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() only returns entities matching rental_control platform."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity("calendar.rental_control_unit1", "on", "Unit 1"),
        _make_entity("sensor.temperature", "22.5", "Temp"),
        _make_entity("calendar.rental_control_unit2", "off", "Unit 2"),
        _make_entity("calendar.family_events", "on", "Family"),
        _make_entity("light.living_room", "on", "Living Room"),
    ]

    registry = [
        _make_registry_entry("calendar.rental_control_unit1"),
        _make_registry_entry("calendar.rental_control_unit2"),
        _make_registry_entry("sensor.temperature", "sensor"),
        _make_registry_entry("calendar.family_events", "google"),
        _make_registry_entry("light.living_room", "hue"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(return_value=registry)

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is True
    assert len(result.integrations) == 2
    entity_ids = [i.entity_id for i in result.integrations]
    assert "calendar.rental_control_unit1" in entity_ids
    assert "calendar.rental_control_unit2" in entity_ids
    assert "sensor.temperature" not in entity_ids
    assert "calendar.family_events" not in entity_ids


@pytest.mark.asyncio
async def test_discover_marks_already_configured(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() sets already_configured=True for entities with existing config."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.models.ha_integration_config import HAIntegrationConfig

    # Pre-configure unit1
    config = HAIntegrationConfig(integration_id="calendar.rental_control_unit1")
    db_session.add(config)
    db_session.commit()

    all_entities = [
        _make_entity("calendar.rental_control_unit1", "on", "Unit 1"),
        _make_entity("calendar.rental_control_unit2", "off", "Unit 2"),
    ]

    registry = [
        _make_registry_entry("calendar.rental_control_unit1"),
        _make_registry_entry("calendar.rental_control_unit2"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(return_value=registry)

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is True
    configured = {i.entity_id: i.already_configured for i in result.integrations}
    assert configured["calendar.rental_control_unit1"] is True
    assert configured["calendar.rental_control_unit2"] is False


@pytest.mark.asyncio
async def test_discover_extracts_state_and_display(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() extracts state and computes state_display."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity("calendar.rental_control_unit1", "on", "Unit 1"),
        _make_entity("calendar.rental_control_unit2", "off", "Unit 2"),
    ]

    registry = [
        _make_registry_entry("calendar.rental_control_unit1"),
        _make_registry_entry("calendar.rental_control_unit2"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(return_value=registry)

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    by_id = {i.entity_id: i for i in result.integrations}
    assert by_id["calendar.rental_control_unit1"].state == "on"
    assert by_id["calendar.rental_control_unit1"].state_display == "Active booking"
    assert by_id["calendar.rental_control_unit2"].state == "off"
    assert by_id["calendar.rental_control_unit2"].state_display == "No active bookings"


@pytest.mark.asyncio
async def test_discover_extracts_event_summary(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() extracts event_summary from attributes.message."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity(
            "calendar.rental_control_unit1",
            "on",
            "Unit 1",
            message="John Smith Booking",
            start_time="2025-10-26T10:00:00+00:00",
            end_time="2025-10-28T10:00:00+00:00",
        ),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(
        return_value=[_make_registry_entry("calendar.rental_control_unit1")]
    )

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    integration = result.integrations[0]
    assert integration.event_summary == "John Smith Booking"
    assert integration.event_start == "2025-10-26T10:00:00+00:00"
    assert integration.event_end == "2025-10-28T10:00:00+00:00"


@pytest.mark.asyncio
async def test_discover_handles_missing_event_attributes(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() sets event fields to None when attributes are missing."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity("calendar.rental_control_unit1", "off", "Unit 1"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(
        return_value=[_make_registry_entry("calendar.rental_control_unit1")]
    )

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    integration = result.integrations[0]
    assert integration.event_summary is None
    assert integration.event_start is None
    assert integration.event_end is None


@pytest.mark.asyncio
async def test_discover_returns_discovery_result(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() returns DiscoveryResult with available=True on success."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import (
        DiscoveryResult,
        HADiscoveryService,
    )

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=[])
    mock_client.get_entity_registry = AsyncMock(return_value=[])

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert isinstance(result, DiscoveryResult)
    assert result.available is True
    assert result.integrations == []
    assert result.error_message is None
    assert result.error_category is None


@pytest.mark.asyncio
async def test_discover_connection_error_returns_unavailable(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """HAConnectionError produces available=False with category 'connection'."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.integrations.ha_errors import HAConnectionError

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(
        side_effect=HAConnectionError(
            user_message="Cannot connect to Home Assistant",
            detail="Connection refused",
        )
    )
    mock_client.get_entity_registry = AsyncMock(return_value=[])

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is False
    assert result.error_message == "Cannot connect to Home Assistant"
    assert result.error_category == "connection"


@pytest.mark.asyncio
async def test_discover_auth_error_returns_unavailable(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """HAAuthenticationError produces available=False with category 'auth'."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.integrations.ha_errors import HAAuthenticationError

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(
        side_effect=HAAuthenticationError(
            user_message="Authentication failed",
            detail="401 Unauthorized",
        )
    )
    mock_client.get_entity_registry = AsyncMock(return_value=[])

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is False
    assert result.error_message == "Authentication failed"
    assert result.error_category == "auth"


@pytest.mark.asyncio
async def test_discover_timeout_error_returns_unavailable(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """HATimeoutError produces available=False with category 'timeout'."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.integrations.ha_errors import HATimeoutError

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(
        side_effect=HATimeoutError(
            user_message="Request timed out",
            detail="ReadTimeout after 10s",
        )
    )
    mock_client.get_entity_registry = AsyncMock(return_value=[])

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is False
    assert result.error_message == "Request timed out"
    assert result.error_category == "timeout"


@pytest.mark.asyncio
async def test_discover_server_error_returns_unavailable(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """HAServerError produces available=False with category 'server_error'."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.integrations.ha_errors import HAServerError

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(
        side_effect=HAServerError(
            user_message="Home Assistant server error",
            detail="HTTP 500",
        )
    )
    mock_client.get_entity_registry = AsyncMock(return_value=[])

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is False
    assert result.error_message == "Home Assistant server error"
    assert result.error_category == "server_error"


@pytest.mark.asyncio
async def test_discover_extracts_friendly_name(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """discover() extracts friendly_name from entity attributes."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity(
            "calendar.rental_control_beach_house",
            "on",
            "Rental Control Beach House",
        ),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(
        return_value=[
            _make_registry_entry("calendar.rental_control_beach_house"),
        ]
    )

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.integrations[0].friendly_name == "Rental Control Beach House"


@pytest.mark.asyncio
async def test_discover_nonstandard_ids_via_registry_platform(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """Entities with non-standard IDs found via registry platform."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity(
            "calendar.beach_house_rental_control",
            "on",
            "Beach House",
        ),
        _make_entity(
            "calendar.other_rental_control_other",
            "off",
            "Other Rental",
        ),
        _make_entity("sensor.temperature", "22.5", "Temp"),
    ]

    registry = [
        _make_registry_entry("calendar.beach_house_rental_control"),
        _make_registry_entry(
            "calendar.other_rental_control_other",
        ),
        _make_registry_entry("sensor.temperature", "sensor"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(return_value=registry)

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is True
    assert len(result.integrations) == 2
    ids = [i.entity_id for i in result.integrations]
    assert "calendar.beach_house_rental_control" in ids
    assert "calendar.other_rental_control_other" in ids
    assert "sensor.temperature" not in ids


@pytest.mark.asyncio
async def test_discover_excludes_wrong_platform_with_prefix(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """Prefix-matching entity excluded when platform is not rental_control."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService

    all_entities = [
        _make_entity(
            "calendar.rental_control_fake",
            "on",
            "Fake Rental Control",
        ),
        _make_entity(
            "calendar.rental_control_real",
            "off",
            "Real Rental",
        ),
    ]

    registry = [
        _make_registry_entry("calendar.rental_control_fake", "google"),
        _make_registry_entry("calendar.rental_control_real"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(return_value=registry)

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is True
    assert len(result.integrations) == 1
    assert result.integrations[0].entity_id == ("calendar.rental_control_real")


@pytest.mark.asyncio
async def test_discover_fallback_to_prefix_on_registry_failure(
    db_engine: Engine,  # noqa: ARG001
    db_session: Session,
) -> None:
    """Falls back to prefix matching when entity registry fails."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_discovery_service import HADiscoveryService
    from captive_portal.integrations.ha_errors import HAServerError

    all_entities = [
        _make_entity("calendar.rental_control_unit1", "on", "Unit 1"),
        _make_entity("calendar.beach_house_rental", "off", "Beach"),
        _make_entity("sensor.temperature", "22.5", "Temp"),
    ]

    mock_client = MagicMock(spec=HAClient)
    mock_client.get_all_states = AsyncMock(return_value=all_entities)
    mock_client.get_entity_registry = AsyncMock(
        side_effect=HAServerError(
            user_message="Server error",
            detail="HTTP 500",
        )
    )

    service = HADiscoveryService(ha_client=mock_client, session=db_session)
    result = await service.discover()

    assert result.available is True
    assert len(result.integrations) == 1
    assert result.integrations[0].entity_id == ("calendar.rental_control_unit1")
