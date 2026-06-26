# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada settings OpenAPI form validation."""

from __future__ import annotations

from types import SimpleNamespace

from captive_portal.api.routes.omada_settings_ui import (
    _set_runtime_omada_config,
    _validate_omada_form,
)


def test_openapi_mode_validation_accepts_supported_values() -> None:
    """Supported backend modes are accepted by form validation."""
    for mode in ("auto", "openapi", "legacy"):
        assert (
            _validate_omada_form(
                "https://ctrl.test:8043",
                "operator",
                "client-id",
                "0123456789ab",
                "legacy-pass",
                "true",
                mode,
                "client-secret",
                "true",
                "/admin/omada-settings/",
            )
            is None
        )


def test_openapi_mode_validation_rejects_invalid_value() -> None:
    """Unsupported backend modes are rejected with an actionable message."""
    assert (
        _validate_omada_form(
            "https://ctrl.test:8043",
            "operator",
            "client-id",
            "0123456789ab",
            "legacy-pass",
            "true",
            "bad",
            "client-secret",
            "true",
            "/admin/omada-settings/",
        )
        == "Backend+mode+must+be+auto,+openapi,+or+legacy"
    )


def test_forced_openapi_accepts_openapi_only_credentials() -> None:
    """Forced OpenAPI mode does not require legacy username/password."""
    assert (
        _validate_omada_form(
            "https://ctrl.test:8043",
            "",
            "client-id",
            "0123456789ab",
            "",
            "false",
            "openapi",
            "client-secret",
            "true",
            "/admin/omada-settings/",
        )
        is None
    )


def test_forced_openapi_requires_new_or_stored_secret() -> None:
    """Forced OpenAPI mode rejects client IDs without any client secret."""
    assert (
        _validate_omada_form(
            "https://ctrl.test:8043",
            "",
            "client-id",
            "0123456789ab",
            "",
            "false",
            "openapi",
            "",
            "false",
            "/admin/omada-settings/",
            client_secret_exists=False,
        )
        == "Client+Secret+is+required+for+OpenAPI+mode"
    )


def test_auto_mode_accepts_openapi_only_credentials() -> None:
    """Auto mode can save OpenAPI-only credentials for probe selection."""
    assert (
        _validate_omada_form(
            "https://ctrl.test:8043",
            "",
            "client-id",
            "0123456789ab",
            "",
            "false",
            "auto",
            "client-secret",
            "true",
            "/admin/omada-settings/",
        )
        is None
    )


def test_runtime_config_update_refreshes_expiry_worker() -> None:
    """Saving settings updates both request adapters and expiry worker config."""
    runtime_config = object()
    worker = SimpleNamespace(omada_config=None)
    state = SimpleNamespace(grant_expiry_service=worker)

    _set_runtime_omada_config(state, runtime_config)

    assert state.omada_config is runtime_config
    assert worker.omada_config is runtime_config
