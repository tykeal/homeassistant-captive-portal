# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for integration tests."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionMiddleware,
    SessionStore,
)


@pytest.fixture
def empty_admin_table(db_session: Session) -> Any:
    """Ensure admin table is empty for the duration of the test."""
    admins = list(db_session.exec(select(AdminUser)).all())
    for admin in admins:
        db_session.delete(admin)
    db_session.commit()
    yield
    admins = list(db_session.exec(select(AdminUser)).all())
    for admin in admins:
        db_session.delete(admin)
    db_session.commit()


@pytest.fixture
def app(db_engine: Engine) -> FastAPI:
    """Integration test app with safe route imports.

    Overrides the root conftest app fixture to gracefully skip routes
    whose dependencies are not available on this branch.
    """
    test_app = FastAPI(title="Captive Portal (Integration Test)")
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)

    # Provide a default mock HAClient so discovery-dependent routes work
    from unittest.mock import AsyncMock, MagicMock

    from captive_portal.integrations.ha_client import HAClient

    mock_ha = MagicMock(spec=HAClient)
    mock_ha.get_all_states = AsyncMock(return_value=[])
    mock_ha.get_entity_registry = AsyncMock(return_value=[])
    test_app.state.ha_client = mock_ha

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

    def get_test_session() -> Generator[Session, None, None]:
        """Yield test database session."""
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient for integration tests."""
    return TestClient(app)
