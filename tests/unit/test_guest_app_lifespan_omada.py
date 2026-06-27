# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest app lifespan Omada wiring.

Validates that the guest app stores ``omada_config`` dict on ``app.state``
when configured in the database, and ``None`` when not.  Guest app
stores its own independent config (not shared with admin app).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.config.settings import AppSettings
from captive_portal.models.portal_config import PortalConfig
from captive_portal.services.config_migration import MigrationResult


class TestGuestLifespanMigrationAndDefaultOmada:
    """Tests guest migration startup and default Omada state."""

    def test_guest_startup_runs_yaml_migration(self) -> None:
        """Guest lifespan runs the YAML to DB migration before DB reads."""
        settings = AppSettings(db_path=":memory:")

        async def migration_side_effect(
            _settings: AppSettings,
            session: Session,
        ) -> MigrationResult:
            """Persist a guest URL so startup proves migration ran before reads."""
            session.add(
                PortalConfig(
                    id=1,
                    guest_external_url="https://guest.example.test",
                )
            )
            session.commit()
            return MigrationResult(guest_url_migrated=True)

        migration = AsyncMock(side_effect=migration_side_effect)

        from captive_portal.guest_app import create_guest_app

        with patch(
            "captive_portal.services.config_migration.migrate_yaml_to_db",
            migration,
        ):
            app = create_guest_app(settings=settings)
            with TestClient(app):
                assert app.state.guest_external_url == "https://guest.example.test"

            migration.assert_awaited_once()
            await_args = migration.await_args
            assert await_args is not None
            call_settings, call_session = await_args.args
            assert call_settings is settings
            assert isinstance(call_session, Session)

    def test_omada_config_is_none_by_default(self) -> None:
        """app.state.omada_config should be None when DB has no config."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with TestClient(app):
            assert app.state.omada_config is None

    def test_no_shared_client_on_state(self) -> None:
        """No OmadaClient or OmadaAdapter should be stored on app.state."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with TestClient(app):
            assert not hasattr(app.state, "omada_client")
            assert not hasattr(app.state, "omada_adapter")


class TestGuestLifespanOmadaNotConfigured:
    """Tests when Omada controller URL is not configured."""

    def test_omada_config_is_none(self) -> None:
        """app.state.omada_config should be None when not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with TestClient(app):
            assert app.state.omada_config is None

    def test_no_errors_when_unconfigured(self, caplog: pytest.LogCaptureFixture) -> None:
        """Guest app should start without errors when Omada is not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with caplog.at_level(logging.WARNING):
            with TestClient(app) as client:
                resp = client.get("/api/live")

        assert resp.status_code == 200
        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR and "omada" in r.message.lower()
        ]
        assert len(error_records) == 0
