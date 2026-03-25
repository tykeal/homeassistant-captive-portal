# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0709 – Integration tests for guest portal error messages and theming.

Verifies that guest-facing error pages:
  - Display clear, user-friendly error messages
  - Apply theming consistently across pages
  - Have localization placeholder structure (i18n-ready strings)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Error message clarity
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestErrorMessageClarity:
    """Error pages must present user-friendly messages."""

    def test_error_page_returns_200(self, client: TestClient) -> None:
        """Error page renders successfully (not a server error itself)."""
        response = client.get("/guest/error?message=Something+went+wrong")
        assert response.status_code == 200

    def test_default_error_message_when_none_provided(self, client: TestClient) -> None:
        """Missing message param falls back to a friendly default."""
        response = client.get("/guest/error")
        assert response.status_code == 200
        assert b"An error occurred. Please try again." in response.content

    def test_custom_error_message_displayed(self, client: TestClient) -> None:
        """Supplied error message appears in the page body."""
        response = client.get("/guest/error?message=Your+code+has+expired")
        assert response.status_code == 200
        assert b"Your code has expired" in response.content

    def test_error_page_contains_try_again_link(self, client: TestClient) -> None:
        """Error page offers a clear 'Try Again' action."""
        response = client.get("/guest/error")
        content = response.content.decode()
        assert "Try Again" in content
        assert "/guest/authorize" in content

    def test_error_page_contains_go_back_action(self, client: TestClient) -> None:
        """Error page offers a 'Go Back' action."""
        response = client.get("/guest/error")
        content = response.content.decode()
        assert "Go Back" in content

    def test_long_error_message_truncated(self, client: TestClient) -> None:
        """Excessively long messages are truncated to prevent UI breakage."""
        long_msg = "A" * 600
        response = client.get(f"/guest/error?message={long_msg}")
        assert response.status_code == 200
        content = response.content.decode()
        assert content.count("A") < 600
        assert "..." in content

    def test_html_in_error_message_stripped(self, client: TestClient) -> None:
        """HTML tags are stripped from error messages (XSS defence-in-depth)."""
        response = client.get("/guest/error", params={"message": "<b>bold</b> text"})
        assert response.status_code == 200
        assert b"<b>" not in response.content
        assert b"text" in response.content


# ---------------------------------------------------------------------------
# Theming consistency
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThemingConsistency:
    """All guest pages must share the same visual theme."""

    _GUEST_PAGES = [
        "/guest/authorize",
        "/guest/welcome",
        "/guest/error",
    ]

    def test_all_guest_pages_render_successfully(self, client: TestClient) -> None:
        """Every guest page returns HTTP 200."""
        for page in self._GUEST_PAGES:
            resp = client.get(page)
            assert resp.status_code == 200, f"{page} returned {resp.status_code}"

    def test_shared_font_family(self, client: TestClient) -> None:
        """All guest pages reference the same base font stack."""
        for page in self._GUEST_PAGES:
            content = client.get(page).content.decode()
            assert "font-family" in content, f"{page} missing font-family"

    def test_shared_gradient_background(self, client: TestClient) -> None:
        """All guest pages apply the branded gradient background."""
        for page in self._GUEST_PAGES:
            content = client.get(page).content.decode()
            assert "linear-gradient" in content, f"{page} missing gradient"

    def test_shared_container_card_pattern(self, client: TestClient) -> None:
        """All guest pages use the .container card layout."""
        for page in self._GUEST_PAGES:
            content = client.get(page).content.decode()
            assert "container" in content, f"{page} missing .container"

    def test_error_page_uses_branded_colors(self, client: TestClient) -> None:
        """Error page uses the branded primary colour in its action button."""
        content = client.get("/guest/error").content.decode()
        assert "#667eea" in content or "667eea" in content


# ---------------------------------------------------------------------------
# Localization / i18n readiness
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLocalizationReadiness:
    """Templates should use patterns amenable to future i18n extraction."""

    def test_error_page_has_lang_attribute(self, client: TestClient) -> None:
        """Error page <html> tag declares a language."""
        content = client.get("/guest/error").content.decode()
        assert 'lang="en"' in content

    def test_authorize_page_has_lang_attribute(self, client: TestClient) -> None:
        """Authorize page <html> tag declares a language."""
        content = client.get("/guest/authorize").content.decode()
        assert 'lang="en"' in content

    def test_welcome_page_has_lang_attribute(self, client: TestClient) -> None:
        """Welcome page <html> tag declares a language."""
        content = client.get("/guest/welcome").content.decode()
        assert 'lang="en"' in content

    def test_error_page_user_facing_strings_are_complete_sentences(
        self, client: TestClient
    ) -> None:
        """User-visible strings should be translatable sentences, not fragments."""
        content = client.get("/guest/error").content.decode()
        # The default message is a complete, translatable sentence
        assert "An error occurred. Please try again." in content

    def test_authorize_page_has_translatable_heading(self, client: TestClient) -> None:
        """Authorize page heading is a full translatable string."""
        content = client.get("/guest/authorize").content.decode()
        assert "WiFi Authorization" in content

    def test_welcome_page_has_translatable_heading(self, client: TestClient) -> None:
        """Welcome page heading is a full translatable string."""
        content = client.get("/guest/welcome").content.decode()
        assert "Connected!" in content

    def test_templates_use_meta_charset_utf8(self, client: TestClient) -> None:
        """Templates declare UTF-8 charset for i18n support."""
        for page in ["/guest/authorize", "/guest/welcome", "/guest/error"]:
            content = client.get(page).content.decode()
            assert 'charset="UTF-8"' in content or "charset=UTF-8" in content
