# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Helper logic for Omada settings UI routes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any

from captive_portal.models.omada_config import OmadaConfig

logger = logging.getLogger("captive_portal.routes.omada_settings")

_CONTROLLER_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{12,64}$")
OMADA_CONFIGURATION_ERROR = "Settings saved, but Omada configuration could not be applied."
OMADA_CONNECTION_ERROR = (
    "Settings saved, but connection test failed. Check controller URL and credentials."
)


@dataclass(frozen=True)
class OmadaFormData:
    """Validated shape of the Omada settings form.

    Attributes:
        controller_url: Stripped controller URL.
        username: Stripped legacy username.
        client_id: Stripped OpenAPI client ID.
        controller_id: Stripped controller ID.
        password: Raw legacy password value.
        password_changed: Whether the password field changed.
        openapi_mode: Backend selection mode.
        client_secret: Raw OpenAPI client secret.
        client_secret_changed: Whether the OpenAPI secret field changed.
        client_secret_exists: Whether an encrypted OpenAPI secret exists.
    """

    controller_url: str
    username: str
    client_id: str
    controller_id: str
    password: str
    password_changed: str
    openapi_mode: str
    client_secret: str
    client_secret_changed: str
    client_secret_exists: bool = False


async def test_omada_connection(app_state: Any) -> str | None:
    """Test live connectivity to the Omada controller.

    Args:
        app_state: FastAPI app.state object.

    Returns:
        ``"connected"``, ``"error"``, or ``None`` if not configured.
    """
    omada_cfg: dict[str, Any] | None = getattr(app_state, "omada_config", None)
    if omada_cfg is None:
        return None

    from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
    from captive_portal.controllers.tp_omada.base_client import OmadaClientError

    if isinstance(omada_cfg, OmadaRuntimeConfig):
        if omada_cfg.selected_backend == "openapi":
            from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient

            try:
                await OpenApiClient(
                    base_url=omada_cfg.base_url,
                    controller_id=omada_cfg.controller_id,
                    client_id=omada_cfg.client_id,
                    client_secret=omada_cfg.client_secret,
                    verify_ssl=omada_cfg.verify_ssl,
                    token_state=omada_cfg.token_state,
                ).get_access_token()
                return "connected"
            except OmadaClientError as exc:
                logger.warning("Omada OpenAPI connection test failed: %s", exc)
                return "error"
        legacy_cfg: dict[str, Any] = {
            "base_url": omada_cfg.base_url,
            "controller_id": omada_cfg.controller_id,
            "username": omada_cfg.username,
            "password": omada_cfg.password,
            "verify_ssl": omada_cfg.verify_ssl,
        }
    else:
        legacy_cfg = omada_cfg

    from captive_portal.controllers.tp_omada.base_client import OmadaClient, OmadaClientError

    try:
        async with OmadaClient(
            base_url=legacy_cfg["base_url"],
            controller_id=legacy_cfg["controller_id"],
            username=legacy_cfg["username"],
            password=legacy_cfg["password"],
            verify_ssl=legacy_cfg.get("verify_ssl", True),
            timeout=10.0,
        ):
            pass
        return "connected"
    except OmadaClientError as exc:
        logger.warning("Omada connection test failed: %s", exc)
        return "error"
    except Exception as exc:
        logger.warning("Omada connection test error: %s", exc)
        return "error"


def validate_omada_form(
    form: OmadaFormData | str,
    *legacy_args: Any,
    client_secret_exists: bool = False,
) -> str | None:
    """Validate Omada settings form inputs.

    Args:
        form: Parsed Omada settings form values, or the legacy
            ``controller_url`` positional value.
        legacy_args: Legacy positional form values retained for
            private test/backward compatibility.
        client_secret_exists: Whether a stored OpenAPI secret exists
            when using the legacy positional calling convention.

    Returns:
        Error message or None.
    """
    if not isinstance(form, OmadaFormData):
        form = _legacy_omada_form_data(form, legacy_args, client_secret_exists)
    return _validate_omada_form_data(form)


def _legacy_omada_form_data(
    controller_url: str,
    legacy_args: tuple[Any, ...],
    client_secret_exists: bool,
) -> OmadaFormData:
    """Build form data from the former positional helper signature.

    Args:
        controller_url: Stripped controller URL.
        legacy_args: Former positional helper arguments.
        client_secret_exists: Whether a stored OpenAPI secret exists.

    Returns:
        Omada form data.

    Raises:
        TypeError: If the legacy argument count is incorrect.
    """
    if len(legacy_args) != 9:
        msg = "legacy Omada validation requires 10 positional arguments"
        raise TypeError(msg)
    (
        username,
        client_id,
        controller_id,
        password,
        password_changed,
        openapi_mode,
        client_secret,
        client_secret_changed,
        _base_url,
    ) = legacy_args
    return OmadaFormData(
        controller_url=controller_url,
        username=str(username),
        client_id=str(client_id),
        controller_id=str(controller_id),
        password=str(password),
        password_changed=str(password_changed),
        openapi_mode=str(openapi_mode),
        client_secret=str(client_secret),
        client_secret_changed=str(client_secret_changed),
        client_secret_exists=client_secret_exists,
    )


def _validate_omada_form_data(form: OmadaFormData) -> str | None:
    """Validate parsed Omada form data.

    Args:
        form: Parsed Omada settings form values.

    Returns:
        Error message or None.
    """
    if form.controller_url:
        from captive_portal.controllers.tp_omada.base_client import (
            OmadaClientError,
            validate_controller_base_url,
        )

        try:
            validate_controller_base_url(form.controller_url)
        except OmadaClientError:
            return "Controller URL must be a valid HTTP or HTTPS URL"

    if form.openapi_mode not in {"auto", "openapi", "legacy"}:
        return "Backend mode must be auto, openapi, or legacy"

    openapi_secret_available = bool(form.client_id) and bool(
        form.client_secret or form.client_secret_exists
    )
    legacy_required = form.openapi_mode == "legacy" or (
        form.openapi_mode == "auto" and not openapi_secret_available
    )

    if form.controller_url and legacy_required and not form.username:
        return "Username is required when controller URL is set"

    if form.controller_id and not _CONTROLLER_ID_PATTERN.match(form.controller_id):
        return "Controller ID must be a hex string (12-64 characters)"

    if (
        form.controller_url
        and legacy_required
        and form.password_changed == "true"
        and not form.password
    ):
        return "Password is required when setting up a new connection"

    if form.openapi_mode == "openapi" and not form.client_id:
        return "Client ID is required for OpenAPI mode"

    if form.openapi_mode == "openapi" and not openapi_secret_available:
        return "Client Secret is required for OpenAPI mode"

    return None


def set_runtime_omada_config(state: Any, runtime_config: Any) -> None:
    """Update runtime Omada config everywhere it is cached.

    Args:
        state: FastAPI application state.
        runtime_config: Selected Omada runtime config or ``None``.
    """
    state.omada_config = runtime_config
    expiry_service = getattr(state, "grant_expiry_service", None)
    if expiry_service is not None:
        expiry_service.omada_config = runtime_config


def client_secret_changed_for_audit(client_secret: str, client_secret_changed: str) -> bool:
    """Return whether audit metadata should record a secret update.

    Args:
        client_secret: Submitted OpenAPI client secret.
        client_secret_changed: Hidden form field indicating a changed secret.

    Returns:
        True only when a non-empty secret was submitted.
    """
    del client_secret_changed
    return bool(client_secret)


def omada_runtime_error_message(runtime_config: Any) -> str | None:
    """Return settings error text when runtime config rebuild failed.

    Args:
        runtime_config: Runtime Omada config returned by the builder.

    Returns:
        Error message when config is unusable, otherwise ``None``.
    """
    if runtime_config is None:
        return OMADA_CONFIGURATION_ERROR
    return None


async def rebuild_runtime_after_save(
    config: OmadaConfig,
    app_state: Any,
    connection_tester: Callable[[Any], Awaitable[str | None]] = test_omada_connection,
) -> str | None:
    """Rebuild runtime Omada config and test connectivity after save.

    Args:
        config: Persisted Omada configuration.
        app_state: FastAPI application state.
        connection_tester: Async callable used to test live connectivity.

    Returns:
        Error message when rebuild or connectivity failed.
    """
    try:
        from captive_portal.config.omada_config import build_omada_config

        new_omada_cfg = await build_omada_config(config, logger)
        set_runtime_omada_config(app_state, new_omada_cfg)
        error_msg = omada_runtime_error_message(new_omada_cfg)
        if error_msg is not None:
            return error_msg
        if await connection_tester(app_state) == "error":
            return OMADA_CONNECTION_ERROR
    except Exception as exc:
        logger.error(
            "Omada config build error after settings update: %s",
            type(exc).__name__,
        )
        return OMADA_CONFIGURATION_ERROR
    return None
