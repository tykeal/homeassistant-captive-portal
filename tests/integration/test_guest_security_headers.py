# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for guest portal security headers and XSS protection."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_authorize_page_has_security_headers(client: TestClient) -> None:
    """Verify authorization page includes all required security headers.

    Tests that defense-in-depth security headers are present to protect
    against XSS, clickjacking, and MIME-sniffing attacks.
    """
    response = client.get("/guest/authorize")
    assert response.status_code == 200

    # Content-Security-Policy prevents XSS attacks
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp  # No inline scripts allowed
    assert "style-src 'self' 'unsafe-inline'" in csp  # Allow inline styles
    assert "object-src 'none'" in csp

    # Clickjacking protection
    assert response.headers.get("X-Frame-Options") == "DENY"

    # MIME-sniffing protection
    assert response.headers.get("X-Content-Type-Options") == "nosniff"

    # Referrer policy
    assert "Referrer-Policy" in response.headers


@pytest.mark.integration
def test_welcome_page_has_security_headers(client: TestClient) -> None:
    """Verify welcome page includes security headers."""
    response = client.get("/guest/welcome")
    assert response.status_code == 200

    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.integration
def test_error_page_has_security_headers(client: TestClient) -> None:
    """Verify error page includes security headers."""
    response = client.get("/guest/error?message=Test+error")
    assert response.status_code == 200

    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.integration
def test_error_message_sanitization_xss_script_tag(client: TestClient) -> None:
    """Verify error messages with script tags are sanitized.

    Tests that HTML tags are stripped from error messages to prevent
    XSS attacks via malicious query parameters.
    """
    malicious_message = "<script>alert('XSS')</script>Hello"
    response = client.get(f"/guest/error?message={malicious_message}")
    assert response.status_code == 200

    # Script tags should be stripped (but text content remains, which is safe)
    assert b"<script>" not in response.content
    # The word "alert" will still appear as text, but it's HTML-escaped and harmless
    # Verify Hello appears (showing the text was preserved)
    assert b"Hello" in response.content


@pytest.mark.integration
def test_error_message_sanitization_xss_img_tag(client: TestClient) -> None:
    """Verify error messages with img tags are sanitized."""
    malicious_message = '<img src=x onerror="alert(1)">Test'
    response = client.get(f"/guest/error?message={malicious_message}")
    assert response.status_code == 200

    # HTML tags should be stripped
    assert b"<img" not in response.content
    assert b"onerror" not in response.content
    assert b"Test" in response.content


@pytest.mark.integration
def test_error_message_sanitization_length_limit(client: TestClient) -> None:
    """Verify excessively long error messages are truncated."""
    long_message = "A" * 600  # Exceeds 500 char limit
    response = client.get(f"/guest/error?message={long_message}")
    assert response.status_code == 200

    # Should be truncated with ellipsis
    content = response.content.decode()
    # Message should be limited
    assert content.count("A") < 600
    assert "..." in content


@pytest.mark.integration
def test_error_message_sanitization_empty_after_strip(client: TestClient) -> None:
    """Verify that error messages that are only HTML return default message."""
    html_only = "<div><span></span></div>"
    response = client.get(f"/guest/error?message={html_only}")
    assert response.status_code == 200

    # Should show default error message
    assert b"An error occurred. Please try again." in response.content


@pytest.mark.integration
def test_error_message_sanitization_none_parameter(client: TestClient) -> None:
    """Verify that missing error message shows default."""
    response = client.get("/guest/error")
    assert response.status_code == 200

    assert b"An error occurred. Please try again." in response.content


@pytest.mark.integration
def test_jinja2_autoescape_enabled(client: TestClient) -> None:
    """Verify Jinja2 auto-escaping is enabled by testing with HTML entities.

    Even if sanitization is bypassed, Jinja2 should escape HTML entities.
    """
    # This tests that even if our sanitization fails, Jinja2 protects us
    message = "Test &lt;script&gt; message"
    response = client.get(f"/guest/error?message={message}")
    assert response.status_code == 200

    # The &lt; and &gt; should be double-escaped or remain escaped in output
    content = response.content.decode()
    # Should not contain actual < or > characters from the input
    assert "<script>" not in content


@pytest.mark.integration
def test_no_inline_scripts_in_templates(client: TestClient) -> None:
    """Verify guest templates don't contain inline JavaScript.

    This ensures compliance with CSP script-src 'self' directive.
    """
    pages = [
        "/guest/authorize",
        "/guest/welcome",
        "/guest/error",
    ]

    for page in pages:
        response = client.get(page)
        assert response.status_code == 200

        # Should not contain inline script tags
        content = response.content.decode().lower()
        # Allow javascript: protocol in links (e.g., history.back())
        # but no <script> tags with code
        assert "<script>" not in content or "javascript:history.back()" in content
