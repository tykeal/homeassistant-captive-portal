# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Legacy setting resolution helpers for YAML-to-DB migration."""

from __future__ import annotations

from typing import Any, Callable

from captive_portal.config.settings_validators import (
    validate_bool_like,
    validate_non_empty_str,
)

MIGRATION_ADDON_MAP: dict[str, str] = {
    "session_idle_timeout": "session_idle_minutes",
    "session_max_duration": "session_max_hours",
    "guest_external_url": "guest_external_url",
    "omada_controller_url": "omada_controller_url",
    "omada_username": "omada_username",
    "omada_password": "omada_password",
    "omada_site_name": "omada_site_name",
    "omada_controller_id": "omada_controller_id",
    "omada_verify_ssl": "omada_verify_ssl",
    "omada_client_id": "omada_client_id",
    "omada_client_secret": "omada_client_secret",
    "omada_openapi_mode": "omada_openapi_mode",
}

MIGRATION_ENV_MAP: dict[str, str] = {
    "CP_SESSION_IDLE_TIMEOUT": "session_idle_minutes",
    "CP_SESSION_MAX_DURATION": "session_max_hours",
    "CP_GUEST_EXTERNAL_URL": "guest_external_url",
    "CP_OMADA_CONTROLLER_URL": "omada_controller_url",
    "CP_OMADA_USERNAME": "omada_username",
    "CP_OMADA_PASSWORD": "omada_password",
    "CP_OMADA_SITE_NAME": "omada_site_name",
    "CP_OMADA_CONTROLLER_ID": "omada_controller_id",
    "CP_OMADA_VERIFY_SSL": "omada_verify_ssl",
    "CP_OMADA_CLIENT_ID": "omada_client_id",
    "CP_OMADA_CLIENT_SECRET": "omada_client_secret",
    "CP_OMADA_OPENAPI_MODE": "omada_openapi_mode",
}

MIGRATION_DEFAULTS: dict[str, Any] = {
    "session_idle_minutes": 30,
    "session_max_hours": 8,
    "guest_external_url": "",
    "omada_controller_url": "",
    "omada_username": "",
    "omada_password": "",
    "omada_site_name": "Default",
    "omada_controller_id": "",
    "omada_verify_ssl": True,
    "omada_client_id": "",
    "omada_client_secret": "",
    "omada_openapi_mode": "auto",
}

OMADA_OPTIONAL_STR_FIELDS: frozenset[str] = frozenset(
    {
        "omada_username",
        "omada_password",
        "omada_controller_id",
        "omada_site_name",
        "omada_client_id",
        "omada_client_secret",
    }
)


def validate_positive_int(value: Any) -> bool:
    """Check if *value* is a positive integer or string representation.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a positive integer.
    """
    if type(value) is int:
        return value >= 1
    if isinstance(value, str) and value.isdigit():
        return int(value) >= 1
    return False


def validate_guest_url(value: Any) -> bool:
    """Check if *value* is a valid guest external URL or empty string.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a valid guest external URL.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if stripped == "":
        return True

    from captive_portal.services.redirect_validator import GuestExternalUrlValidator

    return GuestExternalUrlValidator.validate(stripped).valid


def validate_omada_url(value: Any) -> bool:
    """Check if *value* is a valid Omada controller URL or empty string.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a valid URL (http/https) or empty string.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if stripped == "":
        return True

    from captive_portal.controllers.tp_omada.base_client import (
        OmadaClientError,
        validate_controller_base_url,
    )

    try:
        validate_controller_base_url(stripped)
    except OmadaClientError:
        return False
    return True


def validate_openapi_mode(value: Any) -> bool:
    """Check if *value* is one of the supported Omada backend modes.

    Args:
        value: Candidate value.

    Returns:
        True if the mode is auto, openapi, or legacy.
    """
    return isinstance(value, str) and value.strip().lower() in (
        "auto",
        "openapi",
        "legacy",
    )


MIGRATION_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "session_idle_minutes": validate_positive_int,
    "session_max_hours": validate_positive_int,
    "guest_external_url": validate_guest_url,
    "omada_controller_url": validate_omada_url,
    "omada_username": validate_non_empty_str,
    "omada_password": validate_non_empty_str,
    "omada_controller_id": validate_non_empty_str,
    "omada_site_name": validate_non_empty_str,
    "omada_verify_ssl": validate_bool_like,
    "omada_client_id": validate_non_empty_str,
    "omada_client_secret": validate_non_empty_str,
    "omada_openapi_mode": validate_openapi_mode,
}


def coerce_bool_like(value: Any) -> bool:
    """Coerce a bool-like migration value to ``bool``.

    Args:
        value: Validated bool-like input.

    Returns:
        Boolean value.
    """
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1")


def coerce_stripped_string(value: Any) -> str:
    """Coerce a migration value to a stripped string.

    Args:
        value: Validated input.

    Returns:
        Stripped string value.
    """
    return str(value).strip()


def coerce_lower_string(value: Any) -> str:
    """Coerce a migration value to a stripped lower-case string.

    Args:
        value: Validated input.

    Returns:
        Lower-case stripped string value.
    """
    return str(value).strip().lower()


def coerce_identity(value: Any) -> Any:
    """Return a migration value unchanged.

    Args:
        value: Validated input.

    Returns:
        The original value.
    """
    return value


MIGRATION_COERCERS: dict[str, Callable[[Any], Any]] = {
    "session_idle_minutes": int,
    "session_max_hours": int,
    "guest_external_url": coerce_stripped_string,
    "omada_controller_url": coerce_stripped_string,
    "omada_username": coerce_stripped_string,
    "omada_password": coerce_stripped_string,
    "omada_site_name": coerce_stripped_string,
    "omada_controller_id": coerce_stripped_string,
    "omada_client_id": coerce_stripped_string,
    "omada_client_secret": coerce_stripped_string,
    "omada_openapi_mode": coerce_lower_string,
    "omada_verify_ssl": coerce_bool_like,
}


def coerce_migration_field(field: str, value: Any) -> Any:
    """Coerce a raw migration value to the correct Python type.

    Args:
        field: Migration field name.
        value: Raw value (already validated).

    Returns:
        Coerced value.
    """
    coercer = MIGRATION_COERCERS.get(field, coerce_identity)
    return coercer(value)
