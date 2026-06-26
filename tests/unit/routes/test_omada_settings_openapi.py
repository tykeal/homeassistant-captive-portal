# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada settings OpenAPI form validation."""

from __future__ import annotations

from captive_portal.api.routes.omada_settings_ui import _validate_omada_form


def test_openapi_mode_validation_accepts_supported_values() -> None:
    """Supported backend modes are accepted by form validation."""
    for mode in ("auto", "openapi", "legacy"):
        assert (
            _validate_omada_form(
                "https://ctrl.test:8043",
                "operator",
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
