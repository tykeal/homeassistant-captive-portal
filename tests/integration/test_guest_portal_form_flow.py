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

from .conftest import extract_csrf_token


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
        """GET with clientMac embeds clientMac hidden field."""
        resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        assert resp.status_code == 200
        text = resp.text
        assert 'name="clientMac"' in text
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
        # Step 1: GET to obtain CSRF token from form
        get_resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        csrf_token = extract_csrf_token(get_resp.text)

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

    def test_error_page_retry_url_preserves_omada_params(
        self,
        guest_client: TestClient,
    ) -> None:
        """Error pages after POST include Omada params in retry URL.

        When a POST /authorize fails the rendered error page must link
        back to /guest/authorize with the original Omada query
        parameters so the guest can try again without losing context.
        """
        # Step 1: GET to obtain CSRF token from form
        get_resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF"
            "&site=abc123&gatewayMac=11-22-33-44-55-66&vid=100",
        )
        csrf_token = extract_csrf_token(get_resp.text)

        # Step 2: POST with form data – code is invalid → error
        post_resp = guest_client.post(
            "/guest/authorize",
            data={
                "client_mac": "AA-BB-CC-DD-EE-FF",
                "site": "abc123",
                "gateway_mac": "11-22-33-44-55-66",
                "vid": "100",
                "code": "BADCODE",
                "csrf_token": csrf_token,
            },
        )

        body = post_resp.text
        # The retry URL must contain the original Omada params
        assert "clientMac=AA-BB-CC-DD-EE-FF" in body
        assert "site=abc123" in body
        assert "gatewayMac=11-22-33-44-55-66" in body
        assert "vid=100" in body
        assert "Try Again" in body

    def test_error_page_retry_url_without_optional_params(
        self,
        guest_client: TestClient,
    ) -> None:
        """Only non-empty Omada params appear in the retry URL."""
        get_resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        csrf_token = extract_csrf_token(get_resp.text)

        post_resp = guest_client.post(
            "/guest/authorize",
            data={
                "client_mac": "AA-BB-CC-DD-EE-FF",
                "code": "BADCODE",
                "csrf_token": csrf_token,
            },
        )

        body = post_resp.text
        assert "clientMac=AA-BB-CC-DD-EE-FF" in body
        # Params that were not provided should be absent
        assert "gatewayMac=" not in body
        assert "vid=" not in body

    def test_get_form_submits_via_get(
        self,
        guest_client: TestClient,
    ) -> None:
        """Form uses GET method so the template renders method=get."""
        resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        assert resp.status_code == 200
        assert 'method="get"' in resp.text

    def test_get_submission_continue_param_alias(
        self,
        guest_client: TestClient,
    ) -> None:
        """Hidden continue field uses 'continue' alias."""
        resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        assert 'name="continue"' in resp.text

    def test_get_submission_reaches_code_validation(
        self,
        guest_client: TestClient,
    ) -> None:
        """GET with code and csrf_token triggers authorization.

        The handler should detect form submission, reach code
        validation (410 = voucher not found), proving the GET
        submission path works end-to-end.
        """
        get_resp = guest_client.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        csrf_token = extract_csrf_token(get_resp.text)

        submit_resp = guest_client.get(
            "/guest/authorize"
            f"?clientMac=AA-BB-CC-DD-EE-FF"
            f"&code=TEST123"
            f"&csrf_token={csrf_token}"
            f"&continue=/guest/welcome",
        )

        assert submit_resp.status_code == 410
        body = submit_resp.text.lower()
        assert "unable to determine device mac" not in body
        assert "not found" in body

    def test_get_authorize_characterizes_all_omada_fields(
        self,
        guest_client: TestClient,
    ) -> None:
        """GET form preserves Omada fields, CSRF, continue, and headers."""
        resp = guest_client.get(
            "/guest/authorize"
            "?clientMac=AA-BB-CC-DD-EE-FF"
            "&clientIp=192.0.2.25"
            "&site=686982d482171c5562624ad1"
            "&apMac=11-22-33-44-55-66"
            "&gatewayMac=22-33-44-55-66-77"
            "&radioId=1"
            "&ssidName=GuestWiFi"
            "&vid=100"
            "&t=123456789"
            "&redirectUrl=https://example.test/original"
            "&continue=/guest/welcome",
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "strict-origin"
        assert resp.headers.get("Cache-Control") == "no-store"

        from tests.utils.guest_portal_characterization import normalize_guest_html

        text = normalize_guest_html(resp.text)
        assert 'method="get"' in text
        assert 'name="csrf_token" value="<csrf-token>"' in text
        for name, value in {
            "continue": "/guest/welcome",
            "clientMac": "AA-BB-CC-DD-EE-FF",
            "clientIp": "192.0.2.25",
            "site": "686982d482171c5562624ad1",
            "apMac": "11-22-33-44-55-66",
            "gatewayMac": "22-33-44-55-66-77",
            "radioId": "1",
            "ssidName": "GuestWiFi",
            "vid": "100",
            "t": "123456789",
            "redirectUrl": "https://example.test/original",
        }.items():
            assert f'name="{name}" value="{value}"' in text
