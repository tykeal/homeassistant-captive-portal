# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for TP-Omada authorize flow (fixture-driven)."""

import pytest


@pytest.mark.contract
def test_omada_authorize_request_structure() -> None:
    """Authorize request must include device MAC, expires_at, site_id."""
    # GIVEN: TP-Omada controller client
    # WHEN: calling authorize with required params
    # THEN: request payload matches expected schema
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_authorize_response_success() -> None:
    """Successful authorize returns grant_id and status=active."""
    # GIVEN: mocked Omada API response (fixture)
    # WHEN: parsing authorize response
    # THEN: grant_id extracted, status confirmed
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_authorize_response_error() -> None:
    """Failed authorize returns error code and message."""
    # GIVEN: mocked Omada error response (e.g., invalid MAC)
    # WHEN: parsing response
    # THEN: error code extracted, exception raised
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_authorize_retry_on_timeout() -> None:
    """Authorize should retry with exponential backoff on timeout."""
    # GIVEN: Omada API timing out first 2 attempts
    # WHEN: calling authorize
    # THEN: retries with 1s, 2s delays; succeeds on 3rd
    pytest.skip("Controller adapter not implemented yet")


@pytest.mark.contract
def test_omada_authorize_idempotent() -> None:
    """Repeated authorize calls with same MAC should be idempotent."""
    # GIVEN: existing active grant for MAC
    # WHEN: calling authorize again
    # THEN: returns existing grant_id or updates expiry
    pytest.skip("Controller adapter not implemented yet")
