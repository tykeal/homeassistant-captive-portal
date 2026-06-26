# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Startup selection factory for Omada controller backends."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.openapi_adapter import OpenApiSiteCache
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient, OpenApiTokenState

OmadaBackend = Literal["legacy", "openapi"]
OmadaMode = Literal["auto", "legacy", "openapi"]


class OmadaBackendSelectionError(RuntimeError):
    """Raised when no requested Omada backend can be selected."""


@dataclass(frozen=True)
class OmadaRuntimeConfig:
    """Immutable selected-backend runtime configuration.

    Attributes:
        selected_backend: Backend selected for the current app run.
        selection_reason: Secret-safe selection reason.
        base_url: Controller base URL.
        controller_id: Omada controller ID.
        site_name: Configured site name.
        verify_ssl: Whether to verify TLS.
        username: Legacy username.
        password: Legacy password.
        client_id: OpenAPI client ID.
        client_secret: OpenAPI client secret.
        token_state: Shared OpenAPI token cache.
        site_cache: Shared OpenAPI site cache.
    """

    selected_backend: OmadaBackend
    selection_reason: str
    base_url: str
    controller_id: str
    site_name: str
    verify_ssl: bool
    username: str = ""
    password: str = ""
    client_id: str = ""
    client_secret: str = ""
    token_state: OpenApiTokenState = field(default_factory=OpenApiTokenState)
    site_cache: OpenApiSiteCache | None = None


@dataclass(frozen=True)
class OmadaSelectionInput:
    """Backend selection input from persisted configuration."""

    base_url: str
    controller_id: str
    site_name: str
    verify_ssl: bool
    openapi_mode: str
    username: str = ""
    password: str = ""
    client_id: str = ""
    client_secret: str = ""

    @property
    def legacy_ready(self) -> bool:
        """Return whether legacy credentials are complete."""
        return bool(self.base_url and self.username and self.password)

    @property
    def openapi_ready(self) -> bool:
        """Return whether OpenAPI credentials are complete."""
        return bool(self.base_url and self.client_id and self.client_secret)


async def select_omada_backend(
    selection_input: OmadaSelectionInput,
    logger: logging.Logger,
) -> OmadaRuntimeConfig:
    """Select the Omada backend for this app run.

    Args:
        selection_input: Backend selection inputs.
        logger: Logger for secret-safe diagnostics.

    Returns:
        Immutable runtime config for the selected backend.

    Raises:
        OmadaBackendSelectionError: If requested credentials/probe cannot select a backend.
    """
    mode = _validate_mode(selection_input.openapi_mode)
    if mode == "legacy":
        return _select_legacy(selection_input, "legacy mode requested")
    if mode == "openapi":
        return await _select_forced_openapi(selection_input, logger)
    return await _select_auto(selection_input, logger)


def _validate_mode(mode: str) -> OmadaMode:
    """Validate and normalize an OpenAPI mode value."""
    normalized = mode.strip().lower()
    if normalized not in ("auto", "openapi", "legacy"):
        raise OmadaBackendSelectionError("openapi_mode must be one of: auto, openapi, legacy")
    return normalized  # type: ignore[return-value]


def _select_legacy(selection_input: OmadaSelectionInput, reason: str) -> OmadaRuntimeConfig:
    """Build a legacy runtime config or raise if legacy is unavailable."""
    if not selection_input.legacy_ready:
        raise OmadaBackendSelectionError("Legacy Omada credentials are incomplete")
    return OmadaRuntimeConfig(
        selected_backend="legacy",
        selection_reason=reason,
        base_url=selection_input.base_url,
        controller_id=selection_input.controller_id,
        site_name=selection_input.site_name,
        verify_ssl=selection_input.verify_ssl,
        username=selection_input.username,
        password=selection_input.password,
    )


async def _select_forced_openapi(
    selection_input: OmadaSelectionInput,
    logger: logging.Logger,
) -> OmadaRuntimeConfig:
    """Select forced OpenAPI or raise without fallback."""
    if not selection_input.openapi_ready:
        raise OmadaBackendSelectionError("OpenAPI mode requires client_id and client_secret")
    if not await _probe_openapi(selection_input, logger):
        raise OmadaBackendSelectionError("OpenAPI token probe failed and fallback is disabled")
    return _openapi_runtime(selection_input, "OpenAPI token probe succeeded")


async def _select_auto(
    selection_input: OmadaSelectionInput,
    logger: logging.Logger,
) -> OmadaRuntimeConfig:
    """Select automatic backend using OpenAPI probe and legacy fallback."""
    if selection_input.openapi_ready:
        if await _probe_openapi(selection_input, logger):
            return _openapi_runtime(selection_input, "OpenAPI token probe succeeded")
        if not selection_input.legacy_ready:
            raise OmadaBackendSelectionError(
                "OpenAPI probe failed and no legacy fallback is configured"
            )
        logger.warning("OpenAPI probe failed; falling back to legacy backend")
        return _select_legacy(selection_input, "OpenAPI probe failed; legacy fallback selected")
    if selection_input.client_id or selection_input.client_secret:
        logger.warning("OpenAPI credentials incomplete; falling back to legacy backend")
    return _select_legacy(selection_input, "OpenAPI credentials not configured")


def _openapi_runtime(selection_input: OmadaSelectionInput, reason: str) -> OmadaRuntimeConfig:
    """Build an OpenAPI runtime config."""
    site_cache = OpenApiSiteCache(site_name=selection_input.site_name)
    return OmadaRuntimeConfig(
        selected_backend="openapi",
        selection_reason=reason,
        base_url=selection_input.base_url,
        controller_id=selection_input.controller_id,
        site_name=selection_input.site_name,
        verify_ssl=selection_input.verify_ssl,
        client_id=selection_input.client_id,
        client_secret=selection_input.client_secret,
        site_cache=site_cache,
    )


async def _probe_openapi(selection_input: OmadaSelectionInput, logger: logging.Logger) -> bool:
    """Probe OpenAPI token capability.

    Args:
        selection_input: Backend selection input.
        logger: Logger for secret-safe diagnostics.

    Returns:
        True when an access token can be obtained.
    """
    client = OpenApiClient(
        base_url=selection_input.base_url,
        controller_id=selection_input.controller_id,
        client_id=selection_input.client_id,
        client_secret=selection_input.client_secret,
        verify_ssl=selection_input.verify_ssl,
    )
    try:
        await client.get_access_token()
    except OmadaClientError as exc:
        logger.warning("OpenAPI token probe failed: %s", exc)
        return False
    return True
