# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for guest app custom HTTPException handler.

Verifies that guest portal errors return friendly HTML error pages
instead of raw JSON responses, and that the retry URL preserves
original Omada query parameters.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_app() -> FastAPI:
    """Create guest app for error handler testing."""
    return create_guest_app(
        settings=AppSettings(db_path=":memory:"),
    )


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Test client for the guest app."""
    with TestClient(guest_app, raise_server_exceptions=False) as client:
        yield client


class TestGuestHTTPExceptionHandler:
    """Custom exception handler returns HTML, not JSON."""

    def test_404_returns_html(self, guest_client: TestClient) -> None:
        """A 404 error should render HTML, not JSON."""
        response = guest_client.get("/nonexistent-path")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert b"<html" in response.content

    def test_404_contains_friendly_title(self, guest_client: TestClient) -> None:
        """The 404 page should show a friendly title."""
        response = guest_client.get("/nonexistent-path")
        assert b"The requested resource was not found." in response.content

    def test_404_contains_try_again_link(self, guest_client: TestClient) -> None:
        """The error page should have a Try Again link."""
        response = guest_client.get("/nonexistent-path")
        content = response.content.decode()
        assert "Try Again" in content
        assert "/guest/authorize" in content

    def test_error_page_not_json(self, guest_client: TestClient) -> None:
        """Error responses must not be JSON."""
        response = guest_client.get("/nonexistent-path")
        assert "application/json" not in response.headers.get("content-type", "")

    def test_error_page_retry_url_defaults_to_authorize(self, guest_client: TestClient) -> None:
        """Without retry_query state the retry URL is /guest/authorize."""
        response = guest_client.get("/nonexistent-path")
        content = response.content.decode()
        assert 'href="/guest/authorize"' in content

    def test_error_page_has_no_go_back_button(self, guest_client: TestClient) -> None:
        """The Go Back button with history.back() is removed."""
        response = guest_client.get("/nonexistent-path")
        content = response.content.decode()
        assert "history.back()" not in content
        assert "Go Back" not in content
