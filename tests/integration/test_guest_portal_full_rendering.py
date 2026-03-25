# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for guest portal full rendering.

Validates that guest-facing and admin pages render with proper HTML,
static assets load from /static/themes/, and no broken asset references.
"""

from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.persistence import database


def _make_client() -> tuple[TestClient, str]:
    """Create a TestClient with a temporary database.

    Returns:
        Tuple of (TestClient, db_path) for cleanup.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = AppSettings(db_path=db_path)
    from captive_portal.app import create_app

    app = create_app(settings=settings)
    return TestClient(app, raise_server_exceptions=False), db_path


def test_guest_authorize_page_returns_html() -> None:
    """Guest authorization page should return 200 with HTML form."""
    client, db_path = _make_client()
    try:
        with client:
            resp = client.get("/guest/authorize")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_admin_portal_settings_returns_html_or_401() -> None:
    """Admin portal settings page should respond (may be 401 without auth)."""
    client, db_path = _make_client()
    try:
        with client:
            resp = client.get("/admin/portal-settings/")
            # Either renders HTML (200) or requires auth (401)
            assert resp.status_code in (200, 401)
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_static_themes_css_returns_200() -> None:
    """GET /static/themes/default/admin.css should return 200."""
    client, db_path = _make_client()
    try:
        with client:
            resp = client.get("/static/themes/default/admin.css")
            assert resp.status_code == 200
            content_type = resp.headers.get("content-type", "")
            assert "css" in content_type.lower() or "text" in content_type.lower()
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_guest_error_page_returns_html() -> None:
    """Guest error page should return 200 with HTML."""
    client, db_path = _make_client()
    try:
        with client:
            resp = client.get("/guest/error")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass
