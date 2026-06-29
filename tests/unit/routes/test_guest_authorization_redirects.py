# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization redirect helpers."""

from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4


def test_build_retry_query_uses_current_key_subset() -> None:
    """Retry URLs preserve only the existing non-empty retry keys."""
    from captive_portal.api.routes.guest_authorization.context import GuestOmadaParams
    from captive_portal.api.routes.guest_authorization.redirects import build_retry_query

    params = GuestOmadaParams(
        client_mac="AA",
        client_ip="192.0.2.25",
        site="site",
        redirect_url="https://example.test",
        continue_url="/guest/welcome",
    )

    assert build_retry_query(params) == "clientMac=AA&site=site&continue=%2Fguest%2Fwelcome"


def test_success_redirect_sets_current_cookie_attributes() -> None:
    """Successful authorization keeps current 303, headers, and cookie attributes."""
    from captive_portal.api.routes.guest_authorization.redirects import success_redirect

    grant_id = uuid4()
    response = success_redirect(url="/guest/welcome", grant_id=grant_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/guest/welcome"
    assert response.headers["Referrer-Policy"] == "strict-origin"
    assert response.headers["Cache-Control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert f"grant_id={grant_id}" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=3600" in cookie
    assert "SameSite=strict" in cookie


def test_safe_destination_falls_back_to_root_path() -> None:
    """Unsafe or missing continue URLs fall back to root-path-aware welcome."""
    from captive_portal.api.routes.guest_authorization.redirects import safe_redirect_destination

    request = Mock()
    request.scope = {"root_path": "/root"}
    validator = Mock()
    validator.is_safe.return_value = False

    assert (
        safe_redirect_destination(request, "https://evil.test", validator) == "/root/guest/welcome"
    )
    validator.is_safe.return_value = True
    assert safe_redirect_destination(request, "/ok", validator) == "/ok"
