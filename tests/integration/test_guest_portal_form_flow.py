# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for GET-to-POST MAC passthrough in the guest portal.

Verifies that Omada query parameters (especially clientMac) survive the
GET → hidden-form-field → POST round-trip so the POST handler can
extract the device MAC address without falling back to header sniffing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_client() -> TestClient:
    """Create a guest-app TestClient with an in-memory DB.

    Uses raise_server_exceptions=False because the POST test
    intentionally hits downstream errors (missing portal_config
    table) after MAC extraction succeeds.  We only assert the
    MAC-specific error is absent.
    """
    app = create_guest_app(settings=AppSettings(db_path=":memory:"))
    return TestClient(app, raise_server_exceptions=False)


class TestGuestPortalFormFlow:
    """GET → POST MAC passthrough integration tests."""

    def test_get_authorize_renders_client_mac(self, guest_client: TestClient) -> None:
        """GET with clientMac embeds client_mac hidden field."""
        with guest_client:
            resp = guest_client.get("/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF")
            assert resp.status_code == 200
            text = resp.text
            assert 'name="client_mac"' in text
            assert 'value="AA-BB-CC-DD-EE-FF"' in text

    def test_post_authorize_receives_mac_from_form(self, guest_client: TestClient) -> None:
        """POST with client_mac form field does not fail on MAC extraction.

        The POST will fail for other reasons (invalid code, missing
        tables in the in-memory DB), but should NOT fail with
        "Unable to determine device MAC address".
        """
        with guest_client:
            # Step 1: GET to obtain CSRF token cookie
            get_resp = guest_client.get("/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF")
            csrf_token = get_resp.cookies.get("guest_csrftoken")
            assert csrf_token is not None

            # Step 2: POST with form data including client_mac
            post_resp = guest_client.post(
                "/guest/authorize",
                data={
                    "client_mac": "AA-BB-CC-DD-EE-FF",
                    "code": "TEST123",
                    "csrf_token": csrf_token,
                    "continue_url": "/guest/welcome",
                },
            )

            # MAC extraction must not be the failure reason.
            # The response may be 400 (bad code) or 500 (missing
            # tables in the lightweight in-memory DB) — both are
            # acceptable as long as MAC extraction itself worked.
            body = post_resp.text.lower()
            assert "unable to determine device mac" not in body
