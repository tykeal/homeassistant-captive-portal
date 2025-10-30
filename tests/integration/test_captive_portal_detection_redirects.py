# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for captive portal detection redirects."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_detection() -> FastAPI:
    """Create app with captive portal detection."""
    app = FastAPI()

    # Common detection URLs
    detection_urls = [
        "/generate_204",
        "/gen_204",
        "/connecttest.txt",
        "/hotspot-detect.html",
        "/ncsi.txt",
    ]

    for url in detection_urls:

        @app.get(url)
        async def redirect_to_auth() -> dict[str, str]:
            """Redirect to auth."""
            return {"redirect": "/guest/authorize"}

    @app.get("/guest/authorize")
    async def authorize() -> dict[str, str]:
        """Auth endpoint."""
        return {"status": "ready"}

    return app


class TestCaptivePortalDetectionRedirects:
    """Test detection URL redirects per D18."""

    def test_android_generate_204(self, app_with_detection: FastAPI) -> None:
        """Android captive portal detection."""
        client = TestClient(app_with_detection)

        response = client.get("/generate_204")
        assert response.status_code == 200
        assert response.json()["redirect"] == "/guest/authorize"

    def test_ios_hotspot_detect(self, app_with_detection: FastAPI) -> None:
        """iOS captive portal detection."""
        client = TestClient(app_with_detection)

        response = client.get("/hotspot-detect.html")
        assert response.status_code == 200

    def test_windows_connecttest(self, app_with_detection: FastAPI) -> None:
        """Windows captive portal detection."""
        client = TestClient(app_with_detection)

        response = client.get("/connecttest.txt")
        assert response.status_code == 200

    def test_direct_auth_access(self, app_with_detection: FastAPI) -> None:
        """Direct access to auth page works."""
        client = TestClient(app_with_detection)

        response = client.get("/guest/authorize")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
