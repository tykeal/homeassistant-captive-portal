# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for admin login page CSP compliance.

Verifies that the admin login page contains no inline ``<style>`` blocks
or ``style=`` attributes, so that it works correctly under
``style-src 'self'`` Content-Security-Policy.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def secure_client(db_engine: Any) -> TestClient:
    """Client backed by create_app() with SecurityHeadersMiddleware."""
    from captive_portal.app import create_app

    return TestClient(create_app())


@pytest.mark.integration
class TestAdminLoginCSPCompliance:
    """Admin login page must not use inline styles blocked by CSP."""

    def test_no_inline_style_block(self, secure_client: TestClient) -> None:
        """Login page must not contain an inline <style> element."""
        resp = secure_client.get("/admin/login")
        assert resp.status_code == 200
        content = resp.text.lower()
        assert "<style>" not in content, "Inline <style> blocks are blocked by style-src 'self'"

    def test_no_inline_style_attributes(self, secure_client: TestClient) -> None:
        """Login page must not contain HTML-declared style= attributes."""
        resp = secure_client.get("/admin/login")
        assert resp.status_code == 200
        matches = re.findall(r'\bstyle\s*=\s*["\']', resp.text, re.IGNORECASE)
        assert matches == [], f"Inline style= attributes are blocked by CSP: {matches}"

    def test_setup_form_hidden_via_css_class(self, secure_client: TestClient) -> None:
        """Setup form must use a CSS class (not inline style) to hide itself."""
        resp = secure_client.get("/admin/login")
        assert resp.status_code == 200
        assert 'class="hidden"' in resp.text, (
            "Setup form should use class='hidden' instead of style='display:none'"
        )

    def test_admin_css_contains_login_styles(self, secure_client: TestClient) -> None:
        """admin.css must contain the login-specific classes."""
        resp = secure_client.get("/static/themes/default/admin.css")
        assert resp.status_code == 200
        css = resp.text
        assert ".login-wrapper" in css
        assert ".login-card" in css
        assert ".login-error" in css
        assert ".setup-hint" in css
        assert ".hidden" in css

    def test_csp_style_src_self(self, secure_client: TestClient) -> None:
        """Admin login CSP must include style-src 'self' without unsafe-inline."""
        resp = secure_client.get("/admin/login")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "style-src 'self'" in csp
        assert "'unsafe-inline'" not in csp
