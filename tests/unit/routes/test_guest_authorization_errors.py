# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization error helper behavior."""

from __future__ import annotations

import time

from fastapi.responses import HTMLResponse


def test_sanitize_error_message_preserves_current_rules() -> None:
    """Sanitization defaults, strips tags, and truncates as before."""
    from captive_portal.api.routes.guest_authorization.errors import sanitize_error_message

    assert sanitize_error_message(None) == "An error occurred. Please try again."
    assert sanitize_error_message("<b>Hello</b>") == "Hello"
    assert sanitize_error_message("<div><span></span></div>") == (
        "An error occurred. Please try again."
    )
    assert sanitize_error_message("Keep <broken tag") == "Keep <broken tag"
    assert sanitize_error_message("A" * 600) == ("A" * 500) + "..."


def test_sanitize_error_message_handles_pathological_input_promptly() -> None:
    """Long tag-like input is truncated and stripped promptly."""
    from captive_portal.api.routes.guest_authorization.errors import (
        _strip_html_tags,
        sanitize_error_message,
    )

    message = ("<" * 50_000) + ("tag>" * 50_000)
    long_tag = "prefix" + ("<" * 50_000) + ">" + "suffix"

    start = time.perf_counter()
    sanitized = sanitize_error_message(message)
    stripped = _strip_html_tags(long_tag)
    elapsed = time.perf_counter() - start

    assert sanitized == ("<" * 500) + "..."
    assert stripped == "prefixsuffix"
    assert elapsed < 5.0


def test_security_headers_preserve_route_contract() -> None:
    """Route security headers keep the current guest response contract."""
    from captive_portal.api.routes.guest_authorization.errors import add_security_headers

    response = add_security_headers(HTMLResponse(""))

    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin"
    assert response.headers["Cache-Control"] == "no-store"
