# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for GET-to-POST MAC passthrough in the guest portal.

Verifies that Omada query parameters (especially clientMac) survive the
GET → hidden-form-field → POST round-trip so the POST handler can
extract the device MAC address without falling back to header sniffing.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app
from captive_portal.persistence import database


@pytest.fixture
def guest_client() -> Generator[TestClient, None, None]:
    """Create a guest-app TestClient with a file-backed DB.

    A file-backed DB is used instead of ``:memory:`` because
    SQLite in-memory databases are per-connection, causing
    tables created during lifespan ``init_db`` to be invisible
    to subsequent request sessions.

    Yields:
        TestClient wired to a fully initialised guest app.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_guest_app(settings=AppSettings(db_path=db_path))
    try:
        with TestClient(app) as client:
            yield client
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


class TestGuestPortalFormFlow:
    """GET → POST MAC passthrough integration tests."""

    def test_get_authorize_renders_client_mac(
        self,
        guest_client: TestClient,
    ) -> None:
        """GET with clientMac embeds client_mac hidden field."""
        resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        assert resp.status_code == 200
        text = resp.text
        assert 'name="client_mac"' in text
        assert 'value="AA-BB-CC-DD-EE-FF"' in text

    def test_post_authorize_receives_mac_from_form(
        self,
        guest_client: TestClient,
    ) -> None:
        """POST with client_mac form field passes MAC extraction.

        The handler should reach voucher look-up and return 410
        (voucher not found) rather than 400 (MAC extraction
        failure), proving the form field was read correctly.
        """
        # Step 1: GET to obtain CSRF token cookie
        get_resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
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

        # Handler must pass MAC extraction (no 400) and
        # reach code validation (410 = voucher not found).
        assert post_resp.status_code == 410
        body = post_resp.text.lower()
        assert "unable to determine device mac" not in body
        assert "not found" in body
