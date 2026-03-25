# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for addon startup wiring.

Validates that create_app() with AppSettings produces a fully functional
application with database initialization, health endpoints, and all
existing route prefixes registered.
"""

from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.persistence import database


def test_create_app_with_settings_initializes_db() -> None:
    """create_app(settings) should create database tables on startup."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(
            log_level="info",
            db_path=db_path,
            session_idle_minutes=30,
            session_max_hours=8,
        )

        from captive_portal.app import create_app

        app = create_app(settings=settings)

        # The lifespan should have initialized the database
        with TestClient(app) as client:
            # Check that health endpoint works
            resp = client.get("/api/health")
            assert resp.status_code == 200

            # Check that readiness endpoint works
            resp = client.get("/api/ready")
            assert resp.status_code == 200
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_create_app_health_returns_200() -> None:
    """GET /api/health should return 200."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_create_app_ready_returns_200() -> None:
    """GET /api/ready should return 200 with database check."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/api/ready")
            assert resp.status_code == 200
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_guest_portal_route_not_404() -> None:
    """Guest portal route should respond (not 404)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/guest/authorize")
            assert resp.status_code != 404
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_admin_route_not_404() -> None:
    """Admin portal-settings route should respond (not 404 — may be 401)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/admin/portal-settings/")
            # Route exists but requires auth → 401, not 404
            assert resp.status_code != 404
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_existing_route_prefixes_registered() -> None:
    """All existing route prefixes should still be registered (FR-014)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)

        route_paths = {r.path for r in app.routes if hasattr(r, "path")}

        # Check key route prefixes exist
        expected_prefixes = [
            "/api/health",
            "/api/ready",
            "/guest/authorize",
            "/admin/portal-settings/",
            "/admin/integrations/",
        ]
        for prefix in expected_prefixes:
            assert any(p == prefix or p.startswith(prefix) for p in route_paths), (
                f"Route prefix '{prefix}' not found in {route_paths}"
            )
    finally:
        database.dispose_engine()
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_create_app_without_args_backward_compatible() -> None:
    """create_app() without arguments should still work (backward compat)."""
    from captive_portal.app import create_app

    # This should not raise — uses AppSettings.load() defaults
    app = create_app()
    assert app is not None
    assert app.title == "Captive Portal Guest Access"

    # Clean up
    database.dispose_engine()
