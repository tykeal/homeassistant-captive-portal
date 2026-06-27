# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for double-submit CSRF protection."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

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
