# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for get_omada_adapter dependency function.

Validates per-request adapter construction from ``app.state.omada_config``,
returning ``None`` when config is absent or missing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter
from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient


def _make_request(
    omada_config: dict[str, Any] | None = None, *, has_attr: bool = True
) -> MagicMock:
    """Build a mock Request with ``app.state.omada_config``.

    Args:
        omada_config: The config dict to place on state, or None.
        has_attr: If False, omada_config attribute won't exist on state.

    Returns:
        Mock Request object.
    """
    request = MagicMock()
    state = MagicMock()
    if has_attr:
        state.omada_config = omada_config
    else:
        # Simulate missing attribute
        del state.omada_config
    request.app.state = state
    return request


class TestGetOmadaAdapter:
    """Tests for the get_omada_adapter dependency."""

    def test_returns_adapter_when_config_present(self) -> None:
        """Should construct and return an OmadaAdapter with correct params."""
        config = {
            "base_url": "https://ctrl.local:8043",
            "controller_id": "ctrl-abc",
            "username": "user1",
            "password": "pass1",
            "verify_ssl": False,
            "site_id": "MySite",
        }
        request = _make_request(omada_config=config)
        adapter = get_omada_adapter(request)

        assert adapter is not None
        assert isinstance(adapter, OmadaAdapter)
        assert isinstance(adapter.client, OmadaClient)
        assert adapter.client.base_url == "https://ctrl.local:8043"
        assert adapter.client.controller_id == "ctrl-abc"
        assert adapter.client.username == "user1"
        assert adapter.client.password == "pass1"
        assert adapter.client.verify_ssl is False
        assert adapter.site_id == "MySite"

    def test_returns_none_when_config_is_none(self) -> None:
        """Should return None when omada_config is None."""
        request = _make_request(omada_config=None)
        adapter = get_omada_adapter(request)
        assert adapter is None

    def test_returns_none_when_attr_missing(self) -> None:
        """Should return None when omada_config attribute doesn't exist."""
        request = _make_request(has_attr=False)
        adapter = get_omada_adapter(request)
        assert adapter is None
