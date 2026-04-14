# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for OmadaConfig SQLModel."""

from __future__ import annotations

from sqlmodel import Session

from captive_portal.models.omada_config import OmadaConfig


class TestOmadaConfigDefaults:
    """Tests for OmadaConfig default values."""

    def test_default_id(self) -> None:
        """Default id is 1 (singleton pattern)."""
        config = OmadaConfig()
        assert config.id == 1

    def test_default_controller_url(self) -> None:
        """Default controller_url is empty string."""
        config = OmadaConfig()
        assert config.controller_url == ""

    def test_default_username(self) -> None:
        """Default username is empty string."""
        config = OmadaConfig()
        assert config.username == ""

    def test_default_encrypted_password(self) -> None:
        """Default encrypted_password is empty string."""
        config = OmadaConfig()
        assert config.encrypted_password == ""

    def test_default_site_name(self) -> None:
        """Default site_name is 'Default'."""
        config = OmadaConfig()
        assert config.site_name == "Default"

    def test_default_controller_id(self) -> None:
        """Default controller_id is empty string."""
        config = OmadaConfig()
        assert config.controller_id == ""

    def test_default_verify_ssl(self) -> None:
        """Default verify_ssl is True."""
        config = OmadaConfig()
        assert config.verify_ssl is True


class TestOmadaConfigured:
    """Tests for omada_configured computed property."""

    def test_not_configured_when_all_empty(self) -> None:
        """Returns False when all fields are empty."""
        config = OmadaConfig()
        assert config.omada_configured is False

    def test_not_configured_when_url_missing(self) -> None:
        """Returns False when controller_url is empty."""
        config = OmadaConfig(
            username="user",
            encrypted_password="encrypted",
        )
        assert config.omada_configured is False

    def test_not_configured_when_username_missing(self) -> None:
        """Returns False when username is empty."""
        config = OmadaConfig(
            controller_url="https://omada.example.com",
            encrypted_password="encrypted",
        )
        assert config.omada_configured is False

    def test_not_configured_when_password_missing(self) -> None:
        """Returns False when encrypted_password is empty."""
        config = OmadaConfig(
            controller_url="https://omada.example.com",
            username="user",
        )
        assert config.omada_configured is False

    def test_configured_when_all_set(self) -> None:
        """Returns True when url, username, and encrypted_password are all set."""
        config = OmadaConfig(
            controller_url="https://omada.example.com",
            username="user",
            encrypted_password="encrypted_value",
        )
        assert config.omada_configured is True

    def test_not_configured_with_whitespace_only(self) -> None:
        """Returns False when fields contain only whitespace."""
        config = OmadaConfig(
            controller_url="   ",
            username="   ",
            encrypted_password="   ",
        )
        assert config.omada_configured is False


class TestOmadaConfigPersistence:
    """Tests for OmadaConfig database persistence."""

    def test_round_trip(self, db_session: Session) -> None:
        """Config can be saved and loaded from DB."""
        config = OmadaConfig(
            id=1,
            controller_url="https://omada.test:8043",
            username="testuser",
            encrypted_password="ciphertext123",
            site_name="TestSite",
            controller_id="abcdef123456",
            verify_ssl=False,
        )
        db_session.add(config)
        db_session.commit()

        loaded = db_session.get(OmadaConfig, 1)
        assert loaded is not None
        assert loaded.controller_url == "https://omada.test:8043"
        assert loaded.username == "testuser"
        assert loaded.encrypted_password == "ciphertext123"
        assert loaded.site_name == "TestSite"
        assert loaded.controller_id == "abcdef123456"
        assert loaded.verify_ssl is False

    def test_singleton_pattern(self, db_session: Session) -> None:
        """Only one record with id=1 is expected."""
        config = OmadaConfig(id=1)
        db_session.add(config)
        db_session.commit()

        loaded = db_session.get(OmadaConfig, 1)
        assert loaded is not None
        assert loaded.id == 1
