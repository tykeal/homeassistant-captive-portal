# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration and shared fixtures."""

from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

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
    from captive_portal.models.omada_config import OmadaConfig  # noqa: F401
    from captive_portal.models.portal_config import PortalConfig  # noqa: F401
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

    # Provide a default mock HAClient so discovery-dependent routes work
    from unittest.mock import AsyncMock, MagicMock

    from captive_portal.integrations.ha_client import HAClient

    mock_ha = MagicMock(spec=HAClient)
    mock_ha.get_all_states = AsyncMock(return_value=[])
    test_app.state.ha_client = mock_ha

    # Add session middleware
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)

    # Register routes
    from captive_portal.api.routes import (
        admin_accounts,
        admin_auth,
        admin_logout_ui,
        dashboard_ui,
        docs,
        grants,
        grants_ui,
        guest_portal,
        health,
        integrations,
        integrations_ui,
        omada_settings_ui,
        portal_config,
        portal_settings_ui,
        vouchers,
        vouchers_ui,
    )

    # Initialize the integrations API router's DB engine
    integrations.set_db_engine(db_engine)

    test_app.include_router(admin_accounts.router)
    test_app.include_router(admin_auth.router)
    test_app.include_router(admin_logout_ui.router)
    test_app.include_router(dashboard_ui.router)
    test_app.include_router(docs.router)
    test_app.include_router(grants.router)
    test_app.include_router(grants_ui.router)
    test_app.include_router(guest_portal.router)
    test_app.include_router(health.router)
    test_app.include_router(integrations.router)
    test_app.include_router(omada_settings_ui.router)
    test_app.include_router(portal_config.router)
    test_app.include_router(portal_settings_ui.router)
    test_app.include_router(vouchers.router)
    test_app.include_router(vouchers_ui.router)
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


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[Any, None]:
    """Create async test client for performance testing."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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
