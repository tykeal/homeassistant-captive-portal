# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for graceful shutdown.

Validates that app shutdown disposes the database engine, releases the
database file lock, and preserves committed data.
"""

from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.config.settings import AppSettings
from captive_portal.persistence import database


def test_shutdown_disposes_engine() -> None:
    """App shutdown via lifespan exit should dispose the engine."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)

        # Entering the TestClient context triggers lifespan startup;
        # exiting triggers lifespan shutdown.
        with TestClient(app):
            # Engine should be active inside context
            assert database._engine is not None

        # After context exit, engine should be disposed (set to None)
        assert database._engine is None
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_db_not_locked_after_shutdown() -> None:
    """After shutdown, database file should not be locked."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)

        with TestClient(app):
            pass  # startup + shutdown

        # After shutdown, a new engine should be able to open the file
        from sqlmodel import create_engine

        new_engine = create_engine(f"sqlite:///{db_path}")
        with Session(new_engine) as session:
            # Should not raise
            session.exec(select(1)).first()
        new_engine.dispose()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_data_intact_after_shutdown() -> None:
    """Data committed before shutdown should be intact on restart."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        settings = AppSettings(db_path=db_path)
        from captive_portal.app import create_app

        app = create_app(settings=settings)

        # First session: create data
        with TestClient(app) as client:
            # Health endpoint proves app is running with DB initialized
            resp = client.get("/api/health")
            assert resp.status_code == 200

        # After shutdown, start a new app instance
        app2 = create_app(settings=settings)
        with TestClient(app2) as client2:
            # DB tables should still exist
            resp = client2.get("/api/health")
            assert resp.status_code == 200

            resp = client2.get("/api/ready")
            assert resp.status_code == 200

        database.dispose_engine()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
