# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for external URL redirect generation and fallback."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from captive_portal.app import create_app
from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app

DETECTION_URLS = [
    "/generate_204",
    "/gen_204",
    "/connecttest.txt",
    "/ncsi.txt",
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/success.txt",
]


class TestExternalUrlRedirects:
    """Test redirect generation with configured guest_external_url."""

    @pytest.fixture
    def guest_client_http(self) -> Generator[TestClient, None, None]:
        """Guest client with HTTP external URL."""
        app = create_guest_app(
            settings=AppSettings(
                db_path=":memory:",
                guest_external_url="http://192.168.1.100:8099",
            )
        )
        with TestClient(app) as client:
            yield client

    @pytest.fixture
    def guest_client_https(self) -> Generator[TestClient, None, None]:
        """Guest client with HTTPS external URL."""
        app = create_guest_app(
            settings=AppSettings(
                db_path=":memory:",
                guest_external_url="https://portal.example.com",
            )
        )
        with TestClient(app) as client:
            yield client

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_http_external_url(self, guest_client_http: TestClient, url: str) -> None:
        """All detection endpoints use HTTP external URL in redirect."""
        response = guest_client_http.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "http://192.168.1.100:8099/guest/authorize"

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_https_external_url(self, guest_client_https: TestClient, url: str) -> None:
        """All detection endpoints use HTTPS external URL in redirect."""
        response = guest_client_https.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://portal.example.com/guest/authorize"


class TestRelativeRedirectFallback:
    """Test redirect fallback when guest_external_url is empty."""

    @pytest.fixture
    def guest_client_empty(self) -> Generator[TestClient, None, None]:
        """Guest client with no external URL configured."""
        app = create_guest_app(settings=AppSettings(db_path=":memory:", guest_external_url=""))
        with TestClient(app) as client:
            yield client

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_relative_redirect(self, guest_client_empty: TestClient, url: str) -> None:
        """Detection endpoints fall back to relative /guest/authorize."""
        response = guest_client_empty.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/guest/authorize"


class TestIngressNotAffectedByExternalUrl:
    """Test that ingress app detection is unaffected by guest_external_url."""

    @pytest.fixture
    def ingress_client(self) -> Generator[TestClient, None, None]:
        """Create ingress client — create_app does NOT store guest_external_url."""
        app = create_app(
            settings=AppSettings(
                db_path=":memory:",
                guest_external_url="http://192.168.1.100:8099",
            )
        )
        with TestClient(app) as client:
            yield client

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_ingress_uses_root_path_not_external_url(
        self, ingress_client: TestClient, url: str
    ) -> None:
        """Ingress detection uses root_path, not guest_external_url."""
        response = ingress_client.get(url, follow_redirects=False)
        assert response.status_code == 302
        # Ingress app has no guest_external_url in state, so uses root_path (empty)
        assert response.headers["location"] == "/guest/authorize"
