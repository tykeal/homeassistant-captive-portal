# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for HA Rental Control entity discovery."""

import pytest


@pytest.mark.contract
def test_ha_entity_discovery_request() -> None:
    """Entity discovery request to HA REST API."""
    # GIVEN: HA REST API client
    # WHEN: calling GET /api/states with filter for rental_control entities
    # THEN: request includes Authorization header and accepts JSON
    pytest.skip("HA client not implemented yet")


@pytest.mark.contract
def test_ha_entity_discovery_response_structure() -> None:
    """HA entity list response contains entity_id, state, attributes."""
    # GIVEN: mocked HA API response (fixture)
    # WHEN: parsing response
    # THEN: each entity has entity_id, attributes.slot_code, attributes.start, etc.
    pytest.skip("HA client not implemented yet")


@pytest.mark.contract
def test_ha_entity_event_attributes_validation() -> None:
    """Event sensor attributes must include start, end, slot_name, slot_code."""
    # GIVEN: mocked event entity (sensor.rental_control_abc_event_0)
    # WHEN: extracting attributes
    # THEN: start (datetime), end (datetime), slot_name (string), slot_code (string) present
    pytest.skip("HA client not implemented yet")


@pytest.mark.contract
def test_ha_entity_discovery_unavailable() -> None:
    """HA API unavailable returns timeout or connection error."""
    # GIVEN: HA API not reachable
    # WHEN: calling discovery
    # THEN: timeout exception raised, retry triggered
    pytest.skip("HA client not implemented yet")


@pytest.mark.contract
def test_ha_entity_discovery_empty_result() -> None:
    """No matching rental_control entities returns empty list."""
    # GIVEN: HA instance with no rental_control integrations
    # WHEN: calling discovery
    # THEN: empty list returned, no error
    pytest.skip("HA client not implemented yet")
