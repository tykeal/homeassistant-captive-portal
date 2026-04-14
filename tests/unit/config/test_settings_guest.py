# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for guest_external_url migration loading.

The ``guest_external_url`` field has moved from ``AppSettings`` to the
``PortalConfig`` database model.  These tests verify that the migration
helper (``_load_for_migration``) still reads legacy values correctly.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import patch

from captive_portal.config.settings import AppSettings


class TestGuestUrlMigrationDefaults:
    """Test migration helper defaults for guest_external_url."""

    def test_default_is_empty_string(self) -> None:
        """Migration defaults guest_external_url to empty string."""
        with patch.dict(os.environ, {}, clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/path.json")
        assert legacy["guest_external_url"] == ""


class TestGuestUrlMigrationFromAddon:
    """Test migration reads guest_external_url from addon options."""

    def test_load_from_addon_options(self) -> None:
        """Migration reads guest_external_url from addon options JSON."""
        options: dict[str, Any] = {
            "guest_external_url": "http://192.168.1.100:8099",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                legacy = AppSettings._load_for_migration(options_path=path)
            assert legacy["guest_external_url"] == "http://192.168.1.100:8099"
        finally:
            os.unlink(path)


class TestGuestUrlMigrationFromEnv:
    """Test migration reads guest_external_url from env var."""

    def test_load_from_env_var(self) -> None:
        """Migration reads CP_GUEST_EXTERNAL_URL from environment."""
        env = {"CP_GUEST_EXTERNAL_URL": "http://10.0.0.1:8099"}
        with patch.dict(os.environ, env, clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/path.json")
        assert legacy["guest_external_url"] == "http://10.0.0.1:8099"


class TestGuestUrlMigrationPrecedence:
    """Test three-tier precedence for migration guest_external_url."""

    def test_addon_option_overrides_env_var(self) -> None:
        """Addon option takes precedence over environment variable."""
        options: dict[str, Any] = {
            "guest_external_url": "http://192.168.1.100:8099",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            env = {"CP_GUEST_EXTERNAL_URL": "http://10.0.0.1:9999"}
            with patch.dict(os.environ, env, clear=True):
                legacy = AppSettings._load_for_migration(options_path=path)
            assert legacy["guest_external_url"] == "http://192.168.1.100:8099"
        finally:
            os.unlink(path)
