# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration and shared fixtures."""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine
from sqlalchemy.engine import Engine

from captive_portal.app import create_app
from captive_portal.persistence import database


@pytest.fixture
def db_engine():  # type: ignore[no-untyped-def]
    """Create test database engine (temporary file-based SQLite)."""
    import tempfile
    import os

    # Create a temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Import all models to register them with SQLModel
    from captive_portal.models.access_grant import AccessGrant  # noqa: F401
    from captive_portal.models.admin_session import AdminSession  # noqa: F401
    from captive_portal.models.admin_user import AdminUser  # noqa: F401
    from captive_portal.models.audit_log import AuditLog  # noqa: F401
    from captive_portal.models.ha_integration_config import HAIntegrationConfig  # noqa: F401
    from captive_portal.models.rental_control_event import RentalControlEvent  # noqa: F401
    from captive_portal.models.voucher import Voucher  # noqa: F401

    engine = create_engine(
        f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False}
    )

    # Set the global engine so get_session() works
    database._engine = engine

    # Create all tables
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)

    yield engine

    # Clean up
    engine.dispose()
    database._engine = None
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Create test database session."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def app(db_engine: Engine) -> FastAPI:
    """Create test FastAPI app with database initialized."""
    app_instance = create_app()

    # Override the get_session dependency to use the test database
    def get_test_session() -> Generator[Session, None, None]:
        """Get test database session."""
        with Session(db_engine) as session:
            yield session

    from captive_portal.persistence.database import get_session

    app_instance.dependency_overrides[get_session] = get_test_session

    return app_instance


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client for API testing."""
    return TestClient(app)
