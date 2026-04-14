# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the root ``/`` redirect route.

Verifies that the HA ingress panel landing page redirects to
``/admin/login`` and respects the ingress ``root_path``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.persistence import database


@contextmanager
def _make_client(root_path: str = "") -> Generator[TestClient, None, None]:
    """Create a TestClient backed by a temporary database.

    The temporary database file is removed on cleanup.

    Args:
        root_path: ASGI root_path to simulate HA ingress prefix.

    Yields:
        A configured TestClient instance.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(
            log_level="info",
            db_path=db_path,
        )

        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app, root_path=root_path) as client:
            yield client
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_root_redirects_to_admin_login() -> None:
    """GET / should 303 redirect to /admin/login."""
    with _make_client() as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/login"


def test_root_redirect_respects_ingress_root_path() -> None:
    """GET / with ingress root_path should prefix the redirect target."""
    with _make_client(root_path="/api/hassio_ingress/abc123") as client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/api/hassio_ingress/abc123/admin/login"
