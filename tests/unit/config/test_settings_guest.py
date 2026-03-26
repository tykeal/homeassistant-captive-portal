# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for guest_external_url settings and validation."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from captive_portal.config.settings import AppSettings


class TestGuestExternalUrlDefault:
    """Test guest_external_url field defaults."""

    def test_default_is_empty_string(self) -> None:
        """Guest_external_url defaults to empty string."""
        settings = AppSettings()
        assert settings.guest_external_url == ""

    def test_load_default_is_empty_string(self) -> None:
        """AppSettings.load() defaults guest_external_url to empty string."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/path.json")
        assert settings.guest_external_url == ""


class TestGuestExternalUrlFromAddonOptions:
    """Test loading guest_external_url from addon options JSON."""

    def test_load_from_addon_options(self) -> None:
        """Load guest_external_url from addon options JSON."""
        options: dict[str, Any] = {"guest_external_url": "http://192.168.1.100:8099"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == "http://192.168.1.100:8099"
        finally:
            os.unlink(path)

    def test_load_https_url(self) -> None:
        """Load HTTPS guest_external_url from addon options."""
        options: dict[str, Any] = {"guest_external_url": "https://portal.example.com"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == "https://portal.example.com"
        finally:
            os.unlink(path)


class TestGuestExternalUrlFromEnvVar:
    """Test loading guest_external_url from CP_GUEST_EXTERNAL_URL env var."""

    def test_load_from_env_var(self) -> None:
        """Load guest_external_url from environment variable."""
        env = {"CP_GUEST_EXTERNAL_URL": "http://10.0.0.1:8099"}
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/path.json")
        assert settings.guest_external_url == "http://10.0.0.1:8099"


class TestGuestExternalUrlPrecedence:
    """Test three-tier precedence: addon option > env var > default."""

    def test_addon_option_overrides_env_var(self) -> None:
        """Addon option takes precedence over environment variable."""
        options: dict[str, Any] = {"guest_external_url": "http://192.168.1.100:8099"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            env = {"CP_GUEST_EXTERNAL_URL": "http://10.0.0.1:9999"}
            with patch.dict(os.environ, env, clear=True):
                settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == "http://192.168.1.100:8099"
        finally:
            os.unlink(path)

    def test_env_var_used_when_no_addon_option(self) -> None:
        """Env var used when addon option is absent."""
        options: dict[str, Any] = {}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            env = {"CP_GUEST_EXTERNAL_URL": "http://10.0.0.1:8099"}
            with patch.dict(os.environ, env, clear=True):
                settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == "http://10.0.0.1:8099"
        finally:
            os.unlink(path)

    def test_default_used_when_no_option_and_no_env(self) -> None:
        """Default used when neither addon option nor env var is set."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/path.json")
        assert settings.guest_external_url == ""


class TestGuestExternalUrlValidation:
    """Test validation rules for guest_external_url."""

    def test_empty_string_is_valid(self) -> None:
        """Empty string is valid (means not configured)."""
        settings = AppSettings(guest_external_url="")
        assert settings.guest_external_url == ""

    def test_valid_http_url(self) -> None:
        """HTTP URL is valid."""
        settings = AppSettings(guest_external_url="http://192.168.1.100:8099")
        assert settings.guest_external_url == "http://192.168.1.100:8099"

    def test_valid_https_url(self) -> None:
        """HTTPS URL is valid."""
        settings = AppSettings(guest_external_url="https://portal.example.com")
        assert settings.guest_external_url == "https://portal.example.com"

    def test_invalid_url_wrong_scheme_falls_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid URL with non-http/https scheme falls through to default."""
        options: dict[str, Any] = {"guest_external_url": "ftp://example.com"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)

    def test_invalid_url_trailing_slash_falls_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URL with trailing slash is rejected."""
        options: dict[str, Any] = {"guest_external_url": "http://192.168.1.100:8099/"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)

    def test_whitespace_stripped(self) -> None:
        """Whitespace is stripped from guest_external_url."""
        options: dict[str, Any] = {"guest_external_url": "  http://192.168.1.100:8099  "}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == "http://192.168.1.100:8099"
        finally:
            os.unlink(path)

    def test_invalid_url_no_host_falls_to_default(self, caplog: pytest.LogCaptureFixture) -> None:
        """URL with no host (e.g. http://) is rejected."""
        options: dict[str, Any] = {"guest_external_url": "http://"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)

    def test_invalid_url_with_query_falls_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URL with query string is rejected."""
        options: dict[str, Any] = {"guest_external_url": "http://example.com?x=1"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)

    def test_invalid_url_with_fragment_falls_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URL with fragment is rejected."""
        options: dict[str, Any] = {"guest_external_url": "http://example.com#frag"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)

    def test_invalid_url_with_path_falls_to_default(self, caplog: pytest.LogCaptureFixture) -> None:
        """URL with non-root path is rejected (base URL only)."""
        options: dict[str, Any] = {"guest_external_url": "http://example.com/foo"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(options, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="captive_portal.config"):
                    settings = AppSettings.load(options_path=path)
            assert settings.guest_external_url == ""
            assert "guest_external_url" in caplog.text
        finally:
            os.unlink(path)


class TestGuestExternalUrlLogEffective:
    """Test that log_effective includes guest_external_url."""

    def test_log_effective_includes_guest_external_url(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """log_effective() includes guest_external_url in output."""
        settings = AppSettings(guest_external_url="http://192.168.1.100:8099")
        log = logging.getLogger("test_settings_guest")
        with caplog.at_level(logging.INFO, logger="test_settings_guest"):
            settings.log_effective(log)
        assert "guest_external_url" in caplog.text
        assert "http://192.168.1.100:8099" in caplog.text
