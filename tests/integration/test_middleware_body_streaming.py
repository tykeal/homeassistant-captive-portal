# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Regression test: middleware stack must not break Form() body parsing.

Stacking two BaseHTTPMiddleware subclasses causes call_next() to
double-wrap the ASGI receive channel, making Form() body unreadable.
The guest app previously used two such subclasses (DebugLoggingMiddleware
and SecurityHeadersMiddleware), causing all POST requests with Form data
to return 400 on iOS captive portal authorizations.

This test exercises POST with Form data through the full middleware
stack with debug logging enabled to ensure the body reaches the route
handler intact.
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
def guest_client_debug() -> Generator[TestClient, None, None]:
    """Create a guest-app TestClient with debug logging enabled.

    Both middleware layers are active, reproducing the conditions
    that previously caused Form() body streaming failures.

    Yields:
        TestClient wired to a guest app with debug enabled.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_guest_app(
        settings=AppSettings(
            db_path=db_path,
            debug_guest_portal=True,
        ),
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


class TestMiddlewareBodyStreaming:
    """Ensure middleware stack does not break Form() body parsing."""

    def test_post_form_data_with_debug_middleware(
        self,
        guest_client_debug: TestClient,
    ) -> None:
        """POST with Form data must reach the route handler.

        Regression: two stacked BaseHTTPMiddleware subclasses caused
        Form() parsing to fail with 400. The handler should reach
        voucher validation (410) rather than failing at body
        parsing (400/422).
        """
        get_resp = guest_client_debug.get(
            "/guest/authorize?clientMac=AA-BB-CC-DD-EE-FF",
        )
        assert get_resp.status_code == 200
        csrf_token = extract_csrf_token(get_resp.text)

        post_resp = guest_client_debug.post(
            "/guest/authorize",
            data={
                "client_mac": "AA-BB-CC-DD-EE-FF",
                "code": "TESTCODE",
                "csrf_token": csrf_token,
                "continue_url": "/guest/welcome",
            },
        )

        # Must NOT be 400 (body parsing failure) or 422 (validation)
        assert post_resp.status_code not in (400, 422), (
            f"Form() body parsing failed (status {post_resp.status_code}); "
            "middleware may be consuming the request body"
        )
        # 410 = voucher not found, proving the handler executed
        assert post_resp.status_code == 410
