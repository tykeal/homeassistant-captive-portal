# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada backend startup selection."""

from __future__ import annotations

import logging

import pytest

from captive_portal.controllers.tp_omada import adapter_factory
from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaBackendSelectionError,
    OmadaSelectionInput,
    select_omada_backend,
)


def _input(**overrides: str) -> OmadaSelectionInput:
    """Build default complete selection input."""
    values = {
        "base_url": "https://ctrl.test:8043",
        "controller_id": "0123456789ab",
        "site_name": "Default",
        "verify_ssl": True,
        "openapi_mode": "auto",
        "username": "legacy-user",
        "password": "legacy-pass",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }
    values.update(overrides)
    return OmadaSelectionInput(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_auto_selects_openapi_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatic mode selects OpenAPI when the token probe succeeds."""

    async def probe_success(*_args: object) -> bool:
        """Return successful probe result."""
        return True

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_success)
    runtime = await select_omada_backend(_input(), logging.getLogger(__name__))
    assert runtime.selected_backend == "openapi"


@pytest.mark.asyncio
async def test_auto_falls_back_to_legacy_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automatic mode falls back to legacy when probe fails and legacy is ready."""

    async def probe_failure(*_args: object) -> bool:
        """Return failed probe result."""
        return False

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_failure)
    runtime = await select_omada_backend(_input(), logging.getLogger(__name__))
    assert runtime.selected_backend == "legacy"


@pytest.mark.asyncio
async def test_auto_probe_failure_without_legacy_reports_no_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automatic mode reports probe failure when no legacy fallback exists."""

    async def probe_failure(*_args: object) -> bool:
        """Return failed probe result."""
        return False

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_failure)
    with pytest.raises(OmadaBackendSelectionError, match="OpenAPI probe failed"):
        await select_omada_backend(
            _input(username="", password=""),
            logging.getLogger(__name__),
        )


@pytest.mark.asyncio
async def test_forced_openapi_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forced OpenAPI raises on failed probe instead of selecting legacy."""

    async def probe_failure(*_args: object) -> bool:
        """Return failed probe result."""
        return False

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe_failure)
    with pytest.raises(OmadaBackendSelectionError):
        await select_omada_backend(_input(openapi_mode="openapi"), logging.getLogger(__name__))


@pytest.mark.asyncio
async def test_forced_legacy_skips_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forced legacy selects legacy without probing OpenAPI."""
    called = False

    async def probe(*_args: object) -> bool:
        """Track unexpected probe calls."""
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(adapter_factory, "_probe_openapi", probe)
    runtime = await select_omada_backend(_input(openapi_mode="legacy"), logging.getLogger(__name__))
    assert runtime.selected_backend == "legacy"
    assert called is False
