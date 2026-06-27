# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration coverage for OpenAPI backend selection."""

from __future__ import annotations

import logging
import time

import pytest

from captive_portal.controllers.tp_omada import adapter_factory
from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaSelectionInput,
    select_omada_backend,
)
from captive_portal.controllers.tp_omada.openapi_client import OpenApiTokenState


@pytest.mark.asyncio
async def test_auto_openapi_selection_when_probe_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatic mode selects OpenAPI after a successful token probe."""
    probed_state = OpenApiTokenState(
        access_token="probe-token",
        expires_at_monotonic=time.monotonic() + 7200,
    )

    async def probe_success(*_args: object) -> OpenApiTokenState:
        """Return successful probe token state."""
        return probed_state

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_success)
    runtime = await select_omada_backend(
        OmadaSelectionInput(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            site_name="Default",
            verify_ssl=True,
            openapi_mode="auto",
            username="operator",
            password="legacy-pass",
            client_id="client-id",
            client_secret="client-secret",
        ),
        logging.getLogger(__name__),
    )
    assert runtime.selected_backend == "openapi"
    assert runtime.token_state is probed_state
