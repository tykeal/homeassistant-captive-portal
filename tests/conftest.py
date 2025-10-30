# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration and shared fixtures."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine
from sqlalchemy.engine import Engine

from captive_portal.persistence import database


@pytest.fixture
def db_engine() -> Generator[Engine, None, None]:
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
    # Create app with test-friendly session config
    from captive_portal.security.session_middleware import (
        SessionConfig,
        SessionMiddleware,
        SessionStore,
    )

    test_app = FastAPI(title="Captive Portal Guest Access (Test)")

    # Initialize with test-friendly session config (no secure cookies for HTTP)
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store

    # Add session middleware
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)

    # Register routes
    from captive_portal.api.routes import (
        admin_accounts,
        admin_auth,
        grants,
        guest_portal,
        health,
        integrations_ui,
        vouchers,
    )

    test_app.include_router(admin_accounts.router)
    test_app.include_router(admin_auth.router)
    test_app.include_router(grants.router)
    test_app.include_router(guest_portal.router)
    test_app.include_router(health.router)
    test_app.include_router(vouchers.router)
    test_app.include_router(integrations_ui.router)

    # Override the get_session dependency to use the test database
    def get_test_session() -> Generator[Session, None, None]:
        """Get test database session."""
        with Session(db_engine) as session:
            yield session

    from captive_portal.persistence.database import get_session

    test_app.dependency_overrides[get_session] = get_test_session

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client for API testing."""
    return TestClient(app)


@pytest.fixture
def admin_user(db_session: Session) -> Generator[Any, None, None]:
    """Create a test admin user (available for all tests)."""
    from captive_portal.models.admin_user import AdminUser
    from captive_portal.security.password_hashing import hash_password

    admin = AdminUser(
        username="testadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="testadmin@example.com",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    yield admin
    db_session.delete(admin)
    db_session.commit()
