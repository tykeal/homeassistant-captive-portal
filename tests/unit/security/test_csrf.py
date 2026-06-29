# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for double-submit CSRF protection."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from captive_portal.security.csrf import CSRFProtection


def _make_form_request() -> AsyncMock:
    """Build a request mock that advertises form-encoded data."""
    request = AsyncMock()
    request.headers = {"content-type": "application/x-www-form-urlencoded"}
    return request


@pytest.mark.asyncio
async def test_form_parse_failure_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Form parse failures are logged while preserving non-crashing behavior."""
    csrf = CSRFProtection()
    request = _make_form_request()
    request.form.side_effect = RuntimeError("stream consumed")

    with caplog.at_level(logging.WARNING, logger="captive_portal.security.csrf"):
        token = await csrf._extract_request_token(request)

    assert token is None
    assert "Unable to parse CSRF form token" in caplog.text
    assert "stream consumed" in caplog.text


def test_set_csrf_cookie_accepts_generated_token() -> None:
    """Generated URL-safe CSRF tokens are accepted as cookie values."""
    csrf = CSRFProtection()
    response = Response()
    token = csrf.generate_token()

    csrf.set_csrf_cookie(response, token)

    assert f"csrftoken={token}" in response.headers["set-cookie"]


def test_set_csrf_cookie_rejects_unsafe_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unsafe CSRF token values are rejected before cookie creation."""
    csrf = CSRFProtection()
    response = Response()

    with caplog.at_level(logging.ERROR, logger="captive_portal.security.csrf"):
        with pytest.raises(ValueError, match="unsafe for cookie"):
            csrf.set_csrf_cookie(response, "valid-prefix\r\nSet-Cookie: evil=true")

    assert "Refusing to set invalid CSRF token cookie" in caplog.text
    assert "set-cookie" not in response.headers
