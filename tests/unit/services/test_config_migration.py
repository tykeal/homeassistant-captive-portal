# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config migration service."""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlmodel import Session

from captive_portal.config.settings import AppSettings
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.security.credential_encryption import decrypt_credential
from captive_portal.services.config_migration import MigrationResult, migrate_yaml_to_db


@pytest.fixture
def key_path() -> str:
    """Create temporary key file path for testing.

    Returns:
        Path to a temporary key file.
    """
    fd, path = tempfile.mkstemp(suffix=".key")
    os.close(fd)
    os.unlink(path)  # Start with no key file
    return path


class TestMigrateYamlToDb:
    """Tests for migrate_yaml_to_db()."""

    @pytest.mark.asyncio
    async def test_full_migration_with_all_fields(self, db_session: Session, key_path: str) -> None:
        """All fields migrate from populated AppSettings."""
        settings = AppSettings(
            omada_controller_url="https://omada.test:8043",
            omada_username="operator",
            omada_password="secret123",
            omada_site_name="TestSite",
            omada_controller_id="aabbccdd1122",
            omada_verify_ssl=False,
            session_idle_minutes=45,
            session_max_hours=12,
            guest_external_url="https://guest.example.com",
        )

        result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is True
        assert result.session_fields_migrated == 2
        assert result.guest_url_migrated is True

        # Verify Omada config
        omada = db_session.get(OmadaConfig, 1)
        assert omada is not None
        assert omada.controller_url == "https://omada.test:8043"
        assert omada.username == "operator"
        assert decrypt_credential(omada.encrypted_password, key_path=key_path) == "secret123"
        assert omada.site_name == "TestSite"
        assert omada.verify_ssl is False

        # Verify portal config
        portal = db_session.get(PortalConfig, 1)
        assert portal is not None
        assert portal.session_idle_minutes == 45
        assert portal.session_max_hours == 12
        assert portal.guest_external_url == "https://guest.example.com"

    @pytest.mark.asyncio
    async def test_idempotent_omada_skip(self, db_session: Session, key_path: str) -> None:
        """Omada migration is skipped when DB already has configured record."""
        existing = OmadaConfig(
            id=1,
            controller_url="https://existing.omada:8043",
            username="existing_user",
            encrypted_password="existing_encrypted",
        )
        db_session.add(existing)
        db_session.commit()

        settings = AppSettings(
            omada_controller_url="https://new.omada:8043",
            omada_username="new_user",
            omada_password="new_pass",
        )

        result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is False

        # Verify existing values were NOT overwritten
        omada = db_session.get(OmadaConfig, 1)
        assert omada is not None
        assert omada.controller_url == "https://existing.omada:8043"
        assert omada.username == "existing_user"

    @pytest.mark.asyncio
    async def test_idempotent_session_skip(self, db_session: Session, key_path: str) -> None:
        """Session migration is skipped when DB has non-default values."""
        portal = PortalConfig(id=1, session_idle_minutes=60)
        db_session.add(portal)
        db_session.commit()

        settings = AppSettings(session_idle_minutes=90)

        result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.session_fields_migrated == 0

        # Verify existing value was NOT overwritten
        loaded = db_session.get(PortalConfig, 1)
        assert loaded is not None
        assert loaded.session_idle_minutes == 60

    @pytest.mark.asyncio
    async def test_partial_migration_omada_only(self, db_session: Session, key_path: str) -> None:
        """Only Omada settings migrate when session settings are default."""
        settings = AppSettings(
            omada_controller_url="https://omada.test:8043",
            omada_username="user",
            omada_password="pass",
        )

        result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is True
        assert result.session_fields_migrated == 0
        assert result.guest_url_migrated is False

    @pytest.mark.asyncio
    async def test_empty_settings_apply_defaults(self, db_session: Session, key_path: str) -> None:
        """Default AppSettings result in no migration."""
        settings = AppSettings()

        result = await migrate_yaml_to_db(settings, db_session, key_path=key_path)

        assert result.omada_migrated is False
        assert result.session_fields_migrated == 0
        assert result.guest_url_migrated is False

    @pytest.mark.asyncio
    async def test_migration_result_fields(self, db_session: Session, key_path: str) -> None:
        """MigrationResult has correct field types."""
        result = MigrationResult()
        assert result.omada_migrated is False
        assert result.session_fields_migrated == 0
        assert result.guest_url_migrated is False
        assert result.skipped_reason is None
