# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for post-auth redirect to original destination."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from urllib.parse import quote


@pytest.fixture
def app_with_redirect() -> FastAPI:
    """Create app with redirect handling."""
    app = FastAPI()

    @app.get("/guest/authorize")
    async def authorize(continue_url: str | None = None) -> dict[str, str | None]:
        """Authorization endpoint."""
        return {"continue_url": continue_url}

    return app


class TestPostAuthRedirectOriginalDestination:
    """Test continue URL preservation."""

    def test_preserve_continue_url(self, app_with_redirect: FastAPI) -> None:
        """Continue URL parameter is preserved."""
        client = TestClient(app_with_redirect)

        original_url = "http://example.com/page"
        response = client.get(f"/guest/authorize?continue={quote(original_url)}")

        assert response.status_code == 200
        data = response.json()
        assert data["continue_url"] == original_url

    def test_no_continue_url(self, app_with_redirect: FastAPI) -> None:
        """Missing continue URL is handled."""
        client = TestClient(app_with_redirect)

        response = client.get("/guest/authorize")

        assert response.status_code == 200
        data = response.json()
        assert data["continue_url"] is None
