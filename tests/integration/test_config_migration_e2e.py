# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end integration tests for YAML-to-DB config migration."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest
from sqlmodel import Session

from captive_portal.config.settings import AppSettings
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.security.credential_encryption import decrypt_credential
from captive_portal.services.config_migration import migrate_yaml_to_db


@pytest.fixture
def key_path() -> str:
    """Create temporary key file path for testing.

    Returns:
        Path to a temporary key file.
    """
    fd, path = tempfile.mkstemp(suffix=".key")
    os.close(fd)
    os.unlink(path)
    return path


class TestConfigMigrationE2E:
    """End-to-end migration flow tests."""

    @pytest.mark.asyncio
    async def test_full_startup_migration(self, db_session: Session, key_path: str) -> None:
        """Simulate startup with YAML values → DB records created."""
        env = {
            "CP_OMADA_CONTROLLER_URL": "https://omada.e2e:8043",
            "CP_OMADA_USERNAME": "e2e_user",
            "CP_OMADA_PASSWORD": "e2e_pass",
            "CP_OMADA_SITE_NAME": "E2ESite",
            "CP_OMADA_CONTROLLER_ID": "aabb11223344",
            "CP_OMADA_VERIFY_SSL": "true",
            "CP_SESSION_IDLE_TIMEOUT": "60",
            "CP_SESSION_MAX_DURATION": "24",
            "CP_GUEST_EXTERNAL_URL": "https://guest.e2e.example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings()
            result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is True
        assert result.session_fields_migrated == 2
        assert result.guest_url_migrated is True

        # Verify Omada config in DB
        omada = db_session.get(OmadaConfig, 1)
        assert omada is not None
        assert omada.controller_url == "https://omada.e2e:8043"
        assert omada.username == "e2e_user"
        assert decrypt_credential(omada.encrypted_password, key_path=key_path) == "e2e_pass"

        # Verify portal config in DB
        portal = db_session.get(PortalConfig, 1)
        assert portal is not None
        assert portal.session_idle_minutes == 60
        assert portal.session_max_hours == 24
        assert portal.guest_external_url == "https://guest.e2e.example.com"

    @pytest.mark.asyncio
    async def test_restart_does_not_overwrite(self, db_session: Session, key_path: str) -> None:
        """Simulate restart → DB values unchanged after second migration."""
        env = {
            "CP_OMADA_CONTROLLER_URL": "https://omada.e2e:8043",
            "CP_OMADA_USERNAME": "e2e_user",
            "CP_OMADA_PASSWORD": "e2e_pass",
            "CP_SESSION_IDLE_TIMEOUT": "60",
            "CP_SESSION_MAX_DURATION": "24",
            "CP_GUEST_EXTERNAL_URL": "https://guest.e2e.example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings()

            # First migration
            result1 = await migrate_yaml_to_db(settings, db_session, key_path=key_path)
            assert result1.omada_migrated is True

            # Second migration (simulate restart)
            result2 = await migrate_yaml_to_db(settings, db_session, key_path=key_path)
            assert result2.omada_migrated is False  # Already migrated
            assert result2.session_fields_migrated == 0  # Already non-default

    @pytest.mark.asyncio
    async def test_fresh_install_defaults(self, db_session: Session, key_path: str) -> None:
        """Simulate fresh install — default settings, no migration."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings()

            result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is False
        assert result.session_fields_migrated == 0
        assert result.guest_url_migrated is False

        # Portal config created with defaults
        portal = db_session.get(PortalConfig, 1)
        assert portal is not None
        assert portal.session_idle_minutes == 30
        assert portal.session_max_hours == 8
        assert portal.guest_external_url == ""
