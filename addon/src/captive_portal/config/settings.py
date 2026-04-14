# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Application settings with three-tier precedence.

Loads configuration from:
1. Home Assistant addon options (``/data/options.json``) — highest priority
2. Environment variables with ``CP_`` prefix
3. Built-in defaults — lowest priority

Each field is resolved independently: an invalid addon option for one
field does not affect resolution of other fields.

Settings that have migrated to the web UI / database (Omada controller,
session timeouts, guest external URL) are no longer stored on this
class.  The ``_load_for_migration()`` classmethod reads those legacy
sources once for the one-time YAML→DB migration service.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from pydantic import BaseModel

logger = logging.getLogger("captive_portal.config")

_VALID_LOG_LEVELS = frozenset({"trace", "debug", "info", "notice", "warning", "error", "fatal"})

# HA log level → Python logging level mapping
_HA_TO_PYTHON_LOG_LEVEL: dict[str, int] = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}

# Mapping from addon option keys to AppSettings field names
_ADDON_OPTION_MAP: dict[str, str] = {
    "log_level": "log_level",
    "ha_base_url": "ha_base_url",
    "ha_token": "ha_token",
    "debug_guest_portal": "debug_guest_portal",
}

# Mapping from env var names to AppSettings field names
_ENV_VAR_MAP: dict[str, str] = {
    "CP_LOG_LEVEL": "log_level",
    "CP_DB_PATH": "db_path",
    "CP_HA_BASE_URL": "ha_base_url",
    "CP_HA_TOKEN": "ha_token",
    "CP_DEBUG_GUEST_PORTAL": "debug_guest_portal",
}


# Reverse maps: field name → addon option key / env var name
_FIELD_TO_ADDON_KEY: dict[str, str] = {v: k for k, v in _ADDON_OPTION_MAP.items()}
_FIELD_TO_ENV_KEY: dict[str, str] = {v: k for k, v in _ENV_VAR_MAP.items()}


def _validate_ha_url(value: Any) -> bool:
    """Check if *value* is a valid Home Assistant API URL.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a valid HA base URL.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    from urllib.parse import urlsplit

    parts = urlsplit(stripped)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _validate_bool_like(value: Any) -> bool:
    """Check if *value* is a valid boolean or bool-like string.

    Args:
        value: Candidate value.

    Returns:
        True if the value can be coerced to a boolean.
    """
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.lower() in ("true", "false", "1", "0")
    return False


def _validate_non_empty_str(value: Any) -> bool:
    """Check if *value* is a non-empty stripped string.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a non-empty string after stripping.
    """
    return isinstance(value, str) and len(value.strip()) > 0


# Dispatch table for field validation
_FIELD_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "log_level": lambda v: isinstance(v, str) and v.lower() in _VALID_LOG_LEVELS,
    "db_path": lambda v: isinstance(v, str) and len(v) > 0,
    "ha_base_url": _validate_ha_url,
    "ha_token": _validate_non_empty_str,
    "debug_guest_portal": _validate_bool_like,
}


def _validate_field(field: str, value: Any) -> bool:
    """Validate a single field value.

    Args:
        field: Field name in AppSettings.
        value: Candidate value.

    Returns:
        True if the value is valid for the given field.
    """
    validator = _FIELD_VALIDATORS.get(field)
    if validator is None:
        return False
    return validator(value)


def _coerce_field(field: str, value: Any) -> Any:
    """Coerce a raw value to the correct Python type for a field.

    Args:
        field: Field name in AppSettings.
        value: Raw value (already validated).

    Returns:
        Coerced value suitable for the AppSettings constructor.
    """
    if field == "log_level":
        return str(value).lower()
    if field == "ha_base_url":
        return str(value).strip()
    if field == "ha_token":
        return str(value).strip()
    if field == "debug_guest_portal":
        if isinstance(value, bool):
            return value
        s = str(value).lower()
        return s in ("true", "1")
    return value


def _try_addon_option(field_name: str, addon_key: str, raw: Any) -> tuple[bool, Any]:
    """Attempt to resolve a field from an addon option value.

    Returns ``(True, coerced_value)`` when the value is valid, or
    ``(False, None)`` when the caller should fall through to
    environment / default resolution.

    Args:
        field_name: AppSettings field name.
        addon_key: Corresponding key in ``options.json``.
        raw: Raw value read from addon options.

    Returns:
        Tuple of (resolved, value).
    """
    if _validate_field(field_name, raw):
        return True, _coerce_field(field_name, raw)

    logger.warning(
        "Invalid addon option '%s': %r — ignoring, will try environment variable or default.",
        addon_key,
        raw,
    )
    return False, None


# --- Migration-only maps and validators --------------------------------
# These are used exclusively by ``_load_for_migration()`` to read legacy
# YAML / env var values for the one-time DB migration.  They are *not*
# part of the active ``AppSettings`` class.

_MIGRATION_ADDON_MAP: dict[str, str] = {
    "session_idle_timeout": "session_idle_minutes",
    "session_max_duration": "session_max_hours",
    "guest_external_url": "guest_external_url",
    "omada_controller_url": "omada_controller_url",
    "omada_username": "omada_username",
    "omada_password": "omada_password",
    "omada_site_name": "omada_site_name",
    "omada_controller_id": "omada_controller_id",
    "omada_verify_ssl": "omada_verify_ssl",
}

_MIGRATION_ENV_MAP: dict[str, str] = {
    "CP_SESSION_IDLE_TIMEOUT": "session_idle_minutes",
    "CP_SESSION_MAX_DURATION": "session_max_hours",
    "CP_GUEST_EXTERNAL_URL": "guest_external_url",
    "CP_OMADA_CONTROLLER_URL": "omada_controller_url",
    "CP_OMADA_USERNAME": "omada_username",
    "CP_OMADA_PASSWORD": "omada_password",
    "CP_OMADA_SITE_NAME": "omada_site_name",
    "CP_OMADA_CONTROLLER_ID": "omada_controller_id",
    "CP_OMADA_VERIFY_SSL": "omada_verify_ssl",
}

_MIGRATION_DEFAULTS: dict[str, Any] = {
    "session_idle_minutes": 30,
    "session_max_hours": 8,
    "guest_external_url": "",
    "omada_controller_url": "",
    "omada_username": "",
    "omada_password": "",
    "omada_site_name": "Default",
    "omada_controller_id": "",
    "omada_verify_ssl": True,
}


def _validate_positive_int(value: Any) -> bool:
    """Check if *value* is a positive integer (or string representation).

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


def _validate_guest_url(value: Any) -> bool:
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

    from urllib.parse import urlsplit

    parts = urlsplit(stripped)
    if parts.scheme not in ("http", "https"):
        return False
    if not parts.netloc:
        return False
    if parts.query or parts.fragment:
        return False
    if parts.path and parts.path != "/":
        return False
    if stripped.endswith("/"):
        return False
    return True


def _validate_omada_url(value: Any) -> bool:
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
    from urllib.parse import urlsplit

    parts = urlsplit(stripped)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


_MIGRATION_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "session_idle_minutes": _validate_positive_int,
    "session_max_hours": _validate_positive_int,
    "guest_external_url": _validate_guest_url,
    "omada_controller_url": _validate_omada_url,
    "omada_username": _validate_non_empty_str,
    "omada_password": _validate_non_empty_str,
    "omada_controller_id": _validate_non_empty_str,
    "omada_site_name": _validate_non_empty_str,
    "omada_verify_ssl": _validate_bool_like,
}

# Omada optional string fields: empty string means "unset", not invalid
_OMADA_OPTIONAL_STR_FIELDS: frozenset[str] = frozenset(
    {
        "omada_username",
        "omada_password",
        "omada_controller_id",
        "omada_site_name",
    }
)


def _coerce_migration_field(field: str, value: Any) -> Any:
    """Coerce a raw migration value to the correct Python type.

    Args:
        field: Migration field name.
        value: Raw value (already validated).

    Returns:
        Coerced value.
    """
    if field in ("session_idle_minutes", "session_max_hours"):
        return int(value)
    if field == "guest_external_url":
        return str(value).strip()
    if field in (
        "omada_controller_url",
        "omada_username",
        "omada_password",
        "omada_site_name",
        "omada_controller_id",
    ):
        return str(value).strip()
    if field == "omada_verify_ssl":
        if isinstance(value, bool):
            return value
        s = str(value).lower()
        return s in ("true", "1")
    return value


class AppSettings(BaseModel):
    """Application configuration resolved from addon options, env vars, and defaults."""

    log_level: str = "info"
    db_path: str = "/data/captive_portal.db"
    ha_base_url: str = "http://supervisor/core/api"
    ha_token: str = ""
    debug_guest_portal: bool = False

    @classmethod
    def load(cls, options_path: str = "/data/options.json") -> AppSettings:
        """Load settings with per-field three-tier precedence.

        Resolution order for each field independently:
        1. Addon option from *options_path* (if present and valid)
        2. ``CP_``-prefixed environment variable (if present and valid)
        3. Built-in default

        Args:
            options_path: Path to the HA addon options JSON file.

        Returns:
            Fully resolved ``AppSettings`` instance.
        """
        # --- Layer 1: Read addon options (if file exists) ---
        addon_options: dict[str, Any] = {}
        try:
            with open(options_path) as fh:
                addon_options = json.load(fh)
                if not isinstance(addon_options, dict):
                    addon_options = {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        defaults = cls()
        resolved: dict[str, Any] = {}

        for field_name in (
            "log_level",
            "db_path",
            "ha_base_url",
            "ha_token",
            "debug_guest_portal",
        ):
            # --- Try addon option ---
            addon_key = _FIELD_TO_ADDON_KEY.get(field_name)
            if addon_key and addon_key in addon_options:
                resolved_ok, value = _try_addon_option(
                    field_name,
                    addon_key,
                    addon_options[addon_key],
                )
                if resolved_ok:
                    resolved[field_name] = value
                    continue

            # --- Try environment variable ---
            # ha_token has a special primary source: SUPERVISOR_TOKEN
            if field_name == "ha_token":
                sv_token = os.environ.get("SUPERVISOR_TOKEN")
                if sv_token is not None and _validate_field(field_name, sv_token):
                    resolved[field_name] = _coerce_field(field_name, sv_token)
                    continue

            env_key = _FIELD_TO_ENV_KEY.get(field_name)
            if env_key:
                env_val = os.environ.get(env_key)
                if env_val is not None and _validate_field(field_name, env_val):
                    resolved[field_name] = _coerce_field(field_name, env_val)
                    continue

            # --- Fall through to built-in default ---
            resolved[field_name] = getattr(defaults, field_name)

        return cls(**resolved)

    @classmethod
    def _load_for_migration(
        cls,
        options_path: str = "/data/options.json",
    ) -> dict[str, Any]:
        """Read legacy YAML/env values for the one-time DB migration.

        Returns a dict with keys matching the old field names
        (``omada_controller_url``, ``session_idle_minutes``, etc.)
        resolved via the same three-tier precedence that the old
        ``load()`` used.  This method does **not** store anything on
        the ``AppSettings`` instance.

        Args:
            options_path: Path to the HA addon options JSON file.

        Returns:
            Dict of migrated field names to their resolved values.
        """
        addon_options: dict[str, Any] = {}
        try:
            with open(options_path) as fh:
                addon_options = json.load(fh)
                if not isinstance(addon_options, dict):
                    addon_options = {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        rev_addon: dict[str, str] = {v: k for k, v in _MIGRATION_ADDON_MAP.items()}
        rev_env: dict[str, str] = {v: k for k, v in _MIGRATION_ENV_MAP.items()}

        result: dict[str, Any] = {}

        for field_name, default_val in _MIGRATION_DEFAULTS.items():
            validator = _MIGRATION_VALIDATORS.get(field_name)

            # --- Try addon option ---
            addon_key = rev_addon.get(field_name)
            if addon_key and addon_key in addon_options:
                raw = addon_options[addon_key]
                # Skip empty optional Omada strings
                if (
                    field_name in _OMADA_OPTIONAL_STR_FIELDS
                    and isinstance(raw, str)
                    and raw.strip() == ""
                ):
                    pass
                elif validator and validator(raw):
                    result[field_name] = _coerce_migration_field(field_name, raw)
                    continue

            # --- Try env var ---
            env_key = rev_env.get(field_name)
            if env_key:
                env_val = os.environ.get(env_key)
                if env_val is not None and validator and validator(env_val):
                    result[field_name] = _coerce_migration_field(field_name, env_val)
                    continue

            # --- Default ---
            result[field_name] = default_val

        return result

    def to_log_config(self) -> dict[str, Any]:
        """Return a logging configuration dictionary.

        Returns:
            Dict suitable for ``logging.basicConfig`` keyword arguments.
        """
        python_level = _HA_TO_PYTHON_LOG_LEVEL.get(self.log_level.lower(), logging.INFO)
        return {
            "level": python_level,
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        }

    def log_effective(self, log: logging.Logger) -> None:
        """Log all effective settings at INFO level (no secrets).

        Args:
            log: Logger instance to write to.
        """
        log.info("Effective configuration:")
        log.info("  log_level = %s", self.log_level)
        log.info("  db_path = %s", self.db_path)
        log.info("  ha_base_url = %s", self.ha_base_url)
        log.info("  ha_token = %s", "(set)" if self.ha_token else "(not set)")
        log.info("  debug_guest_portal = %s", self.debug_guest_portal)

    def validate_db_path(self) -> None:
        """Validate that the database path's parent directory exists and is writable.

        Skips validation for SQLite in-memory databases (``:memory:``).

        Raises:
            RuntimeError: If the parent directory does not exist or is not writable.
        """
        if self.db_path == ":memory:":
            return

        from pathlib import Path

        abs_db_path = os.path.abspath(self.db_path)
        parent = Path(abs_db_path).parent
        if not parent.is_dir():
            msg = f"Database directory does not exist for db_path='{self.db_path}': {parent}"
            raise RuntimeError(msg)
        if not os.access(str(parent), os.W_OK | os.X_OK):
            msg = f"Database directory is not writable for db_path='{self.db_path}': {parent}"
            raise RuntimeError(msg)
