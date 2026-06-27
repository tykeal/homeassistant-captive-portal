# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration coverage for forced Omada backend modes."""

from __future__ import annotations

import logging

import pytest

from captive_portal.controllers.tp_omada import adapter_factory
from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaBackendSelectionError,
    OmadaSelectionInput,
    select_omada_backend,
)


@pytest.mark.asyncio
async def test_forced_openapi_missing_credentials_fails() -> None:
    """Forced OpenAPI reports missing credentials instead of falling back."""
    with pytest.raises(OmadaBackendSelectionError):
        await select_omada_backend(
            OmadaSelectionInput(
                base_url="https://ctrl.test:8043",
                controller_id="0123456789ab",
                site_name="Default",
                verify_ssl=True,
                openapi_mode="openapi",
                username="operator",
                password="legacy-pass",
            ),
            logging.getLogger(__name__),
        )


@pytest.mark.asyncio
async def test_forced_openapi_probe_failure_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forced OpenAPI does not select legacy when the token probe fails."""

    async def probe_failure(*_args: object) -> None:
        """Return failed probe result."""
        return None

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_failure)
    with pytest.raises(OmadaBackendSelectionError):
        await select_omada_backend(
            OmadaSelectionInput(
                base_url="https://ctrl.test:8043",
                controller_id="0123456789ab",
                site_name="Default",
                verify_ssl=True,
                openapi_mode="openapi",
                username="operator",
                password="legacy-pass",
                client_id="client-id",
                client_secret="client-secret",
            ),
            logging.getLogger(__name__),
        )
