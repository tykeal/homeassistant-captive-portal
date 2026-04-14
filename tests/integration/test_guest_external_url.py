# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for external URL redirect generation and fallback.

After the YAML cleanup, ``guest_external_url`` is loaded from the
``PortalConfig`` database model during guest app lifespan startup.
These tests verify that redirect behaviour remains correct when the
database contains the expected values.
"""

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


class TestRelativeRedirectFallback:
    """Test redirect fallback when guest_external_url is empty (default)."""

    @pytest.fixture
    def guest_client_empty(self) -> Generator[TestClient, None, None]:
        """Guest client with no external URL configured."""
        app = create_guest_app(settings=AppSettings(db_path=":memory:"))
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
            settings=AppSettings(db_path=":memory:"),
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
