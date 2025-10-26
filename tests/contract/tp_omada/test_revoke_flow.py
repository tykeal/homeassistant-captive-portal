# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for TP-Omada revoke flow (fixture-driven)."""

import pytest


@pytest.mark.contract
def test_omada_revoke_request_structure() -> None:
    """Revoke request must include grant_id or device MAC."""
    # GIVEN: TP-Omada controller client
    # WHEN: calling revoke with grant_id
    # THEN: request payload matches expected schema
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_revoke_response_success() -> None:
    """Successful revoke returns status=revoked."""
    # GIVEN: mocked Omada API response (fixture)
    # WHEN: parsing revoke response
    # THEN: status confirmed as revoked
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_revoke_response_not_found() -> None:
    """Revoke on non-existent grant returns not_found error."""
    # GIVEN: mocked Omada error response (grant_id not found)
    # WHEN: parsing response
    # THEN: NOT_FOUND error code extracted
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_revoke_retry_on_timeout() -> None:
    """Revoke should retry with exponential backoff on timeout."""
    # GIVEN: Omada API timing out first attempt
    # WHEN: calling revoke
    # THEN: retries with 1s delay; succeeds on 2nd
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_revoke_idempotent() -> None:
    """Repeated revoke calls should be idempotent (no error on already revoked)."""
    # GIVEN: already revoked grant
    # WHEN: calling revoke again
    # THEN: returns success or no-op status
    pytest.skip("Controller adapter not implemented yet")
