# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test HA integration entity mapping model."""

import pytest


def test_entity_mapping_integration_id_unique() -> None:
    """Each HA integration can have only one mapping config."""
    # GIVEN: existing mapping for integration_id="rental_control_airbnb"
    # WHEN: creating second mapping for same integration_id
    # THEN: unique constraint violation
    pytest.skip("Model not implemented yet")


def test_entity_mapping_identifier_attr_enum() -> None:
    """Identifier attribute must be slot_code or slot_name."""
    # GIVEN: valid and invalid identifier_attr values
    # WHEN: creating mapping
    # THEN: slot_code/slot_name accepted, others rejected
    pytest.skip("Model not implemented yet")


def test_entity_mapping_last_sync_utc() -> None:
    """Last sync timestamp must be UTC."""
    # GIVEN: mapping with last_sync_utc
    # WHEN: persisting and retrieving
    # THEN: timestamp remains UTC
    pytest.skip("Model not implemented yet")


def test_entity_mapping_stale_count_increments() -> None:
    """Stale count increments on each missed HA poll."""
    # GIVEN: mapping with stale_count=0
    # WHEN: HA poll fails
    # THEN: stale_count increments
    pytest.skip("Model not implemented yet")


def test_entity_mapping_stale_threshold() -> None:
    """After 3 stale polls, degraded warning; after 6, booking grants blocked."""
    # GIVEN: mapping with stale_count >= 6
    # WHEN: attempting booking-based grant
    # THEN: rejected with integration_unavailable
    pytest.skip("Model not implemented yet")
