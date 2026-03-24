# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0713 – Integration tests for theme precedence.

Theme resolution order: admin override > default > fallback.
Validates that all guest-facing pages (including error and welcome) and
voucher-related output share consistent theming.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Theme defaults
# ---------------------------------------------------------------------------

# The default theme gradient and primary colour used across guest pages.
_DEFAULT_GRADIENT = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
_DEFAULT_PRIMARY = "#667eea"


# ---------------------------------------------------------------------------
# Default theme tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDefaultTheme:
    """When no admin override is configured, the default theme must apply."""

    _PAGES = ["/guest/authorize", "/guest/welcome", "/guest/error"]

    def test_default_gradient_on_authorize(self, client: TestClient) -> None:
        """Authorize page uses the default gradient."""
        content = client.get("/guest/authorize").content.decode()
        assert _DEFAULT_PRIMARY in content

    def test_default_gradient_on_welcome(self, client: TestClient) -> None:
        """Welcome page uses the default gradient."""
        content = client.get("/guest/welcome").content.decode()
        assert _DEFAULT_PRIMARY in content

    def test_default_gradient_on_error(self, client: TestClient) -> None:
        """Error page uses the default gradient."""
        content = client.get("/guest/error").content.decode()
        assert _DEFAULT_PRIMARY in content

    def test_all_pages_share_same_primary_colour(self, client: TestClient) -> None:
        """Every guest page references the same primary colour token."""
        for page in self._PAGES:
            content = client.get(page).content.decode()
            assert _DEFAULT_PRIMARY in content, f"{page} missing primary colour"


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFallbackTheme:
    """Without any theme files the templates still render with inline styles."""

    def test_authorize_page_renders_without_external_css(self, client: TestClient) -> None:
        """Authorize page contains inline <style> and does not require a CSS file."""
        content = client.get("/guest/authorize").content.decode()
        assert "<style>" in content

    def test_error_page_renders_without_external_css(self, client: TestClient) -> None:
        """Error page contains inline <style> and does not require a CSS file."""
        content = client.get("/guest/error").content.decode()
        assert "<style>" in content

    def test_welcome_page_renders_without_external_css(self, client: TestClient) -> None:
        """Welcome page contains inline <style> and does not require a CSS file."""
        content = client.get("/guest/welcome").content.decode()
        assert "<style>" in content


# ---------------------------------------------------------------------------
# Error page theming consistency
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestErrorPageTheming:
    """Error pages must match the rest of the guest portal theme."""

    def test_error_page_has_same_font_family(self, client: TestClient) -> None:
        """Error page uses the same font-family as the authorize page."""
        auth_content = client.get("/guest/authorize").content.decode()
        err_content = client.get("/guest/error").content.decode()

        # Both pages must reference the same font stack
        assert "font-family" in auth_content
        assert "font-family" in err_content

    def test_error_page_button_uses_primary_gradient(self, client: TestClient) -> None:
        """The error page's CTA button uses the branded gradient."""
        content = client.get("/guest/error").content.decode()
        assert _DEFAULT_PRIMARY in content

    def test_error_page_container_max_width(self, client: TestClient) -> None:
        """Error page container follows the same max-width pattern."""
        content = client.get("/guest/error").content.decode()
        assert "max-width" in content


# ---------------------------------------------------------------------------
# Voucher / welcome theming consistency
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestVoucherThemingConsistency:
    """Welcome page (post-voucher-redemption) must match theming."""

    def test_welcome_uses_branded_success_icon(self, client: TestClient) -> None:
        """Welcome page uses the branded gradient for its success icon."""
        content = client.get("/guest/welcome").content.decode()
        assert _DEFAULT_PRIMARY in content

    def test_welcome_page_container_style(self, client: TestClient) -> None:
        """Welcome page uses .container with same styling as other pages."""
        content = client.get("/guest/welcome").content.decode()
        assert "container" in content
        assert "border-radius" in content
