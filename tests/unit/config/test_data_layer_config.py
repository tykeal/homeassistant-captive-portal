# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for data-layer configuration helpers."""

from __future__ import annotations

import json
import logging
from unittest.mock import mock_open, patch

import pytest

from captive_portal.config import omada_config
from captive_portal.config.omada_config import build_omada_config
from captive_portal.config.settings import (
    AppSettings,
    _coerce_bool_field,
    _validate_field,
    _validate_ha_url,
)
from captive_portal.config.settings_migration import (
    coerce_bool_like,
    coerce_migration_field,
    validate_guest_url,
    validate_omada_url,
    validate_positive_int,
)
from captive_portal.config.settings_validators import validate_bool_like
from captive_portal.controllers.tp_omada import base_client
from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaBackendSelectionError,
    OmadaRuntimeConfig,
    OmadaSelectionInput,
)
from captive_portal.models.omada_config import OmadaConfig


@pytest.fixture(autouse=True)
def _stub_omada_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub Omada credential decryption to avoid host key-file I/O."""
    monkeypatch.setattr(
        omada_config,
        "decrypt_credential",
        lambda ciphertext: f"plain-{ciphertext}",
    )


def test_settings_primitive_validators_cover_rejections_and_bool_branches() -> None:
    """Primitive settings validators reject invalid values and accept booleans."""
    assert validate_bool_like(True) is True
    assert validate_bool_like("false") is True
    assert validate_bool_like(1) is False
    assert _validate_ha_url(123) is False
    assert _validate_ha_url("   ") is False
    assert _validate_ha_url("https://ha.example.test") is True
    assert _validate_field("unknown", "value") is False
    assert _coerce_bool_field(True) is True
    assert _coerce_bool_field("1") is True


def test_migration_validators_cover_edge_cases() -> None:
    """Migration validators and coercers handle valid and invalid inputs."""
    assert validate_positive_int(1) is True
    assert validate_positive_int("2") is True
    assert validate_positive_int(0) is False
    assert validate_positive_int("0") is False
    assert validate_positive_int(True) is False
    assert validate_guest_url(123) is False
    assert validate_guest_url("   ") is True
    assert validate_guest_url("http://guest.example.test") is True
    assert validate_omada_url(123) is False
    assert validate_omada_url("   ") is True
    assert validate_omada_url("https://omada.example.test:8043") is True
    assert coerce_bool_like(True) is True
    assert coerce_bool_like("true") is True
    assert coerce_bool_like("0") is False
    assert coerce_migration_field("unknown", {"raw": "value"}) == {"raw": "value"}


def test_settings_load_ignores_non_mapping_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """AppSettings.load falls back to environment values for non-object JSON."""
    monkeypatch.setenv("CP_LOG_LEVEL", "debug")

    with patch("builtins.open", mock_open(read_data="[]")):
        settings = AppSettings.load(options_path="ignored.json")

    assert settings.log_level == "debug"


def test_migration_load_ignores_non_mapping_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Migration loading treats non-object options JSON as absent."""
    monkeypatch.delenv("CP_SESSION_IDLE_TIMEOUT", raising=False)

    with patch("builtins.open", mock_open(read_data="[]")):
        values = AppSettings._load_for_migration(options_path="ignored.json")

    assert values["session_idle_minutes"] == 30


def test_migration_load_skips_empty_optional_omada_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty optional Omada addon strings fall through to environment values."""
    monkeypatch.setenv("CP_OMADA_USERNAME", "env-user")
    options = json.dumps({"omada_username": "   "})

    with patch("builtins.open", mock_open(read_data=options)):
        values = AppSettings._load_for_migration(options_path="ignored.json")

    assert values["omada_username"] == "env-user"


@pytest.mark.asyncio
async def test_build_omada_config_returns_none_when_no_backend_configured() -> None:
    """Omada runtime config is absent when neither backend is configured."""
    runtime = await build_omada_config(OmadaConfig(), logging.getLogger(__name__))

    assert runtime is None


@pytest.mark.asyncio
async def test_build_omada_config_discovers_controller_and_selects_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omada config auto-discovers a missing controller ID before selection."""
    selected_inputs: list[OmadaSelectionInput] = []

    async def fake_discover(base_url: str, verify_ssl: bool) -> str:
        """Return a valid controller ID for discovery requests."""
        assert base_url == "https://omada.example.test:8043"
        assert verify_ssl is False
        return "abcdef123456"

    async def fake_select(
        selection_input: OmadaSelectionInput,
        logger: logging.Logger,
    ) -> OmadaRuntimeConfig:
        """Capture selection input and return a deterministic runtime config."""
        selected_inputs.append(selection_input)
        return OmadaRuntimeConfig(
            selected_backend="legacy",
            selection_reason="test selection",
            base_url=selection_input.base_url,
            controller_id=selection_input.controller_id,
            site_name=selection_input.site_name,
            verify_ssl=selection_input.verify_ssl,
            username=selection_input.username,
            password=selection_input.password,
        )

    monkeypatch.setattr(base_client, "discover_controller_id", fake_discover)
    monkeypatch.setattr(omada_config, "select_omada_backend", fake_select)
    monkeypatch.setattr(
        omada_config, "decrypt_credential", lambda ciphertext: f"plain-{ciphertext}"
    )

    runtime = await build_omada_config(
        OmadaConfig(
            controller_url=" https://omada.example.test:8043 ",
            username=" operator ",
            encrypted_password="legacy",
            site_name=" Main ",
            verify_ssl=False,
        ),
        logging.getLogger(__name__),
    )

    assert runtime is not None
    assert runtime.controller_id == "abcdef123456"
    assert selected_inputs[0].password == "plain-legacy"
    assert selected_inputs[0].username == "operator"
    assert selected_inputs[0].site_name == "Main"


@pytest.mark.asyncio
async def test_build_omada_config_returns_none_when_discovery_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Discovery failures produce no runtime config and log safe diagnostics."""

    async def fail_discover(base_url: str, verify_ssl: bool) -> str:
        """Raise the Omada client discovery error."""
        raise base_client.OmadaClientError(f"cannot reach {base_url}; ssl={verify_ssl}")

    monkeypatch.setattr(base_client, "discover_controller_id", fail_discover)
    caplog.set_level(logging.ERROR, logger="test.omada")

    runtime = await build_omada_config(
        OmadaConfig(
            controller_url="https://omada.example.test:8043",
            username="operator",
            encrypted_password="legacy",
        ),
        logging.getLogger("test.omada"),
    )

    assert runtime is None
    assert "Failed to auto-discover Omada controller ID" in caplog.text


@pytest.mark.asyncio
async def test_build_omada_config_returns_none_for_invalid_controller_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid persisted controller IDs are rejected before backend selection."""
    caplog.set_level(logging.ERROR, logger="test.omada")

    runtime = await build_omada_config(
        OmadaConfig(
            controller_url="https://omada.example.test:8043",
            username="operator",
            encrypted_password="legacy",
            controller_id="not-safe",
        ),
        logging.getLogger("test.omada"),
    )

    assert runtime is None
    assert "Omada controller ID failed validation" in caplog.text


@pytest.mark.asyncio
async def test_build_omada_config_returns_none_when_backend_selection_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Backend selection errors are converted into an absent runtime config."""

    async def fail_select(
        selection_input: OmadaSelectionInput,
        logger: logging.Logger,
    ) -> OmadaRuntimeConfig:
        """Raise a backend selection failure for a valid selection input."""
        raise OmadaBackendSelectionError(f"unavailable for {selection_input.controller_id}")

    monkeypatch.setattr(omada_config, "select_omada_backend", fail_select)
    caplog.set_level(logging.ERROR, logger="test.omada")

    runtime = await build_omada_config(
        OmadaConfig(
            controller_url="https://omada.example.test:8043",
            username="operator",
            encrypted_password="legacy",
            controller_id="abcdef123456",
        ),
        logging.getLogger("test.omada"),
    )

    assert runtime is None
    assert "Omada backend selection failed" in caplog.text


def test_decrypt_optional_handles_empty_ciphertext() -> None:
    """Optional credential decryption returns an empty string for absent secrets."""
    assert omada_config._decrypt_optional("", "secret", logging.getLogger(__name__)) == ""
