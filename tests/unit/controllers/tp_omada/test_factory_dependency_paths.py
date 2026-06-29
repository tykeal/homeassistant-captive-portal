# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Focused tests for Omada backend selection and dependency construction."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from captive_portal.controllers.tp_omada import adapter_factory
from captive_portal.controllers.tp_omada.adapter_factory import (
    OmadaBackendSelectionError,
    OmadaRuntimeConfig,
    OmadaSelectionInput,
    select_omada_backend,
)
from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.dependencies import build_omada_adapter
from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.controllers.tp_omada.openapi_adapter import OmadaOpenApiAdapter
from captive_portal.controllers.tp_omada.openapi_client import OpenApiTokenState


def _selection_input(**overrides: object) -> OmadaSelectionInput:
    """Build a complete backend-selection input."""
    values: dict[str, Any] = {
        "base_url": "https://ctrl.test",
        "controller_id": "ctrl",
        "site_name": "Default",
        "verify_ssl": False,
        "openapi_mode": "auto",
        "username": "operator",
        "password": "secret",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }
    values.update(overrides)
    return OmadaSelectionInput(**values)


@pytest.mark.asyncio
async def test_select_backend_rejects_invalid_and_incomplete_modes() -> None:
    """Backend selection rejects invalid modes and incomplete forced credentials."""
    logger = logging.getLogger("tests.omada")

    with pytest.raises(OmadaBackendSelectionError, match="openapi_mode"):
        await select_omada_backend(_selection_input(openapi_mode="invalid"), logger)
    with pytest.raises(OmadaBackendSelectionError, match="Legacy"):
        await select_omada_backend(
            _selection_input(openapi_mode="legacy", username=""),
            logger,
        )
    with pytest.raises(OmadaBackendSelectionError, match="client_id"):
        await select_omada_backend(
            _selection_input(openapi_mode="openapi", client_id=""),
            logger,
        )


@pytest.mark.asyncio
async def test_select_backend_forced_openapi_probe_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced OpenAPI mode raises when the token probe fails."""
    logger = logging.getLogger("tests.omada")

    async def fail_probe(
        _selection_input: OmadaSelectionInput,
        _logger: logging.Logger,
    ) -> OpenApiTokenState | None:
        """Return no token state to simulate a failed probe."""
        return None

    monkeypatch.setattr(adapter_factory, "_probe_openapi", fail_probe)

    with pytest.raises(OmadaBackendSelectionError, match="fallback is disabled"):
        await select_omada_backend(_selection_input(openapi_mode="openapi"), logger)


@pytest.mark.asyncio
async def test_select_backend_forced_openapi_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced OpenAPI mode returns a runtime config after a successful probe."""
    logger = logging.getLogger("tests.omada")
    token_state = OpenApiTokenState(access_token="probe-token")

    async def succeed_probe(
        _selection_input: OmadaSelectionInput,
        _logger: logging.Logger,
    ) -> OpenApiTokenState | None:
        """Return a populated token state to simulate a successful probe."""
        return token_state

    monkeypatch.setattr(adapter_factory, "_probe_openapi", succeed_probe)

    runtime = await select_omada_backend(_selection_input(openapi_mode="openapi"), logger)

    assert runtime.selected_backend == "openapi"
    assert runtime.token_state is token_state


@pytest.mark.asyncio
async def test_select_backend_auto_without_openapi_uses_legacy() -> None:
    """Auto mode falls back to legacy when no OpenAPI credentials exist."""
    logger = logging.getLogger("tests.omada")

    runtime = await select_omada_backend(
        _selection_input(client_id="", client_secret=""),
        logger,
    )

    assert runtime.selected_backend == "legacy"
    assert runtime.selection_reason == "OpenAPI credentials not configured"


@pytest.mark.asyncio
async def test_probe_openapi_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAPI probing returns token state on success and None on client errors."""
    logger = logging.getLogger("tests.omada")

    class SuccessfulClient:
        """OpenAPI client double that populates the provided token state."""

        def __init__(self, **kwargs: object) -> None:
            """Capture and populate the token state argument."""
            self.token_state = cast(OpenApiTokenState, kwargs["token_state"])

        async def get_access_token(self) -> str:
            """Populate and return a probe access token."""
            self.token_state.access_token = "probe-token"
            return "probe-token"

    monkeypatch.setattr(adapter_factory, "OpenApiClient", SuccessfulClient)
    token_state = await adapter_factory._probe_openapi(_selection_input(), logger)
    assert token_state is not None
    assert token_state.access_token == "probe-token"

    class FailingClient:
        """OpenAPI client double that raises during token probing."""

        def __init__(self, **_kwargs: object) -> None:
            """Accept the production constructor arguments."""

        async def get_access_token(self) -> str:
            """Raise a client error for probe failure."""
            raise OmadaClientError("probe failed")

    monkeypatch.setattr(adapter_factory, "OpenApiClient", FailingClient)
    assert await adapter_factory._probe_openapi(_selection_input(), logger) is None


def test_build_omada_adapter_from_runtime_configs() -> None:
    """Runtime configs construct the selected OpenAPI or legacy adapter."""
    token_state = OpenApiTokenState(access_token="token")
    openapi_runtime = OmadaRuntimeConfig(
        selected_backend="openapi",
        selection_reason="test",
        base_url="https://ctrl.test",
        controller_id="ctrl",
        site_name="Default",
        verify_ssl=False,
        client_id="client-id",
        client_secret="client-secret",
        token_state=token_state,
    )
    legacy_runtime = OmadaRuntimeConfig(
        selected_backend="legacy",
        selection_reason="test",
        base_url="https://ctrl.test",
        controller_id="ctrl",
        site_name="Default",
        verify_ssl=False,
        username="operator",
        password="secret",
    )

    openapi_adapter = build_omada_adapter(openapi_runtime)
    legacy_adapter = build_omada_adapter(legacy_runtime)

    assert isinstance(openapi_adapter, OmadaOpenApiAdapter)
    assert openapi_adapter.client.token_state is token_state
    assert isinstance(legacy_adapter, OmadaLegacyAdapter)
    assert legacy_adapter.client.username == "operator"


def test_get_omada_adapter_reads_runtime_from_request_state() -> None:
    """Dependency construction reads runtime config from app state."""
    from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter

    runtime = OmadaRuntimeConfig(
        selected_backend="legacy",
        selection_reason="test",
        base_url="https://ctrl.test",
        controller_id="ctrl",
        site_name="Default",
        verify_ssl=False,
        username="operator",
        password="secret",
    )
    request = MagicMock()
    request.app.state = SimpleNamespace(omada_config=runtime)

    assert isinstance(get_omada_adapter(request), OmadaLegacyAdapter)
