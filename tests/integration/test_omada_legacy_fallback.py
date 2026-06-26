# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration coverage for legacy fallback selection."""

from __future__ import annotations

import logging

import pytest

from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaSelectionInput,
    select_omada_backend,
)


@pytest.mark.asyncio
async def test_legacy_only_configuration_selects_legacy() -> None:
    """Legacy-only deployments require no OpenAPI credentials."""
    runtime = await select_omada_backend(
        OmadaSelectionInput(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            site_name="Default",
            verify_ssl=True,
            openapi_mode="auto",
            username="operator",
            password="legacy-pass",
        ),
        logging.getLogger(__name__),
    )
    assert runtime.selected_backend == "legacy"
