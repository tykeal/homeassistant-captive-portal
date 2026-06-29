# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization form helper behavior."""

from __future__ import annotations

from unittest.mock import Mock

from captive_portal.api.routes.guest_authorization.context import GuestOmadaParams


def test_submission_detection_requires_code_and_csrf() -> None:
    """GET submissions require both code and csrf_token values."""
    from captive_portal.api.routes.guest_authorization.form import is_get_submission

    assert is_get_submission("CODE123", "token") is True
    assert is_get_submission("CODE123", None) is False
    assert is_get_submission(None, "token") is False
    assert is_get_submission("", "token") is False


def test_effective_continue_prefers_continue_then_redirect() -> None:
    """Effective continue keeps current continue/redirect/fallback priority."""
    from captive_portal.api.routes.guest_authorization.form import effective_continue_url

    request = Mock()
    request.scope = {"root_path": "/root"}
    params = GuestOmadaParams(continue_url="/provided", redirect_url="/redirect")
    assert effective_continue_url(request, params) == "/provided"

    params = GuestOmadaParams(redirect_url="/redirect")
    assert effective_continue_url(request, params) == "/redirect"

    params = GuestOmadaParams()
    assert effective_continue_url(request, params) == "/root/guest/welcome"
