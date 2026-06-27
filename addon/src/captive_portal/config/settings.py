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

from captive_portal.config.settings_migration import (
    MIGRATION_ADDON_MAP,
    MIGRATION_DEFAULTS,
    MIGRATION_ENV_MAP,
    MIGRATION_VALIDATORS,
    OMADA_OPTIONAL_STR_FIELDS,
    coerce_migration_field,
)
from captive_portal.config.settings_validators import (
    validate_bool_like,
    validate_non_empty_str,
)

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


_FIELD_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "log_level": lambda v: isinstance(v, str) and v.lower() in _VALID_LOG_LEVELS,
    "db_path": lambda v: isinstance(v, str) and len(v) > 0,
    "ha_base_url": _validate_ha_url,
    "ha_token": validate_non_empty_str,
    "debug_guest_portal": validate_bool_like,
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


def _coerce_bool_field(value: Any) -> bool:
    """Coerce a bool-like setting value to ``bool``.

    Args:
        value: Validated bool-like input.

    Returns:
        Boolean value.
    """
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1")


def _coerce_lower_string(value: Any) -> str:
    """Coerce a setting value to a lower-case string.

    Args:
        value: Validated input.

    Returns:
        Lower-case string value.
    """
    return str(value).lower()


def _coerce_stripped_string(value: Any) -> str:
    """Coerce a setting value to a stripped string.

    Args:
        value: Validated input.

    Returns:
        Stripped string value.
    """
    return str(value).strip()


_FIELD_COERCERS: dict[str, Callable[[Any], Any]] = {
    "log_level": _coerce_lower_string,
    "ha_base_url": _coerce_stripped_string,
    "ha_token": _coerce_stripped_string,
    "debug_guest_portal": _coerce_bool_field,
}


def _coerce_field(field: str, value: Any) -> Any:
    """Coerce a raw value to the correct Python type for a field.

    Args:
        field: Field name in AppSettings.
        value: Raw value (already validated).

    Returns:
        Coerced value suitable for the AppSettings constructor.
    """
    coercer = _FIELD_COERCERS.get(field)
    return value if coercer is None else coercer(value)


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


class AppSettings(BaseModel):
    """Application configuration resolved from addon options, env vars, and defaults."""

    log_level: str = "info"
    db_path: str = "/data/captive_portal.db"
    # aislop-ignore-next-line ai-slop/hardcoded-url -- stable HA Supervisor endpoint
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

        rev_addon: dict[str, str] = {v: k for k, v in MIGRATION_ADDON_MAP.items()}
        rev_env: dict[str, str] = {v: k for k, v in MIGRATION_ENV_MAP.items()}

        result: dict[str, Any] = {}

        for field_name, default_val in MIGRATION_DEFAULTS.items():
            validator = MIGRATION_VALIDATORS.get(field_name)

            addon_key = rev_addon.get(field_name)
            if addon_key and addon_key in addon_options:
                raw = addon_options[addon_key]
                # Skip empty optional Omada strings
                if (
                    field_name in OMADA_OPTIONAL_STR_FIELDS
                    and isinstance(raw, str)
                    and raw.strip() == ""
                ):
                    pass
                elif validator and validator(raw):
                    result[field_name] = coerce_migration_field(field_name, raw)
                    continue

            env_key = rev_env.get(field_name)
            if env_key:
                env_val = os.environ.get(env_key)
                if env_val is not None and validator and validator(env_val):
                    result[field_name] = coerce_migration_field(field_name, env_val)
                    continue

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
