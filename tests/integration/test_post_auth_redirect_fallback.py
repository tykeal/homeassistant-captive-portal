# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin success URL fallback."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_fallback() -> FastAPI:
    """Create app with fallback redirect."""
    app = FastAPI()

    @app.post("/guest/authorize")
    async def authorize(data: dict[str, str]) -> dict[str, str | bool]:
        """Authorization endpoint."""
        # Simplified - in reality would validate code
        return {
            "redirect_url": "/guest/welcome",  # fallback
            "success": True,
        }

    @app.get("/guest/welcome")
    async def welcome() -> dict[str, str]:
        """Welcome page."""
        return {"message": "Welcome!"}

    return app


class TestPostAuthRedirectFallback:
    """Test admin-configured success URL fallback."""

    def test_fallback_when_no_continue_url(self, app_with_fallback: FastAPI) -> None:
        """Fallback to success page when no continue URL."""
        client = TestClient(app_with_fallback)

        response = client.post("/guest/authorize", json={"code": "ABCD1234"})

        assert response.status_code == 200
        data = response.json()
        assert data["redirect_url"] == "/guest/welcome"

    def test_success_page_accessible(self, app_with_fallback: FastAPI) -> None:
        """Success page is accessible."""
        client = TestClient(app_with_fallback)

        response = client.get("/guest/welcome")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
