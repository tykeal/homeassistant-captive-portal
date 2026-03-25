# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Application settings with three-tier precedence.

Loads configuration from:
1. Home Assistant addon options (``/data/options.json``) — highest priority
2. Environment variables with ``CP_`` prefix
3. Built-in defaults — lowest priority

Each field is resolved independently: an invalid addon option for one
field does not affect resolution of other fields.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel

from captive_portal.security.session_middleware import SessionConfig

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
    "session_idle_timeout": "session_idle_minutes",
    "session_max_duration": "session_max_hours",
}

# Mapping from env var names to AppSettings field names
_ENV_VAR_MAP: dict[str, str] = {
    "CP_LOG_LEVEL": "log_level",
    "CP_DB_PATH": "db_path",
    "CP_SESSION_IDLE_TIMEOUT": "session_idle_minutes",
    "CP_SESSION_MAX_DURATION": "session_max_hours",
}


def _validate_field(field: str, value: Any) -> bool:
    """Validate a single field value.

    Args:
        field: Field name in AppSettings.
        value: Candidate value.

    Returns:
        True if the value is valid for the given field.
    """
    if field == "log_level":
        return isinstance(value, str) and value.lower() in _VALID_LOG_LEVELS
    if field == "db_path":
        return isinstance(value, str) and len(value) > 0
    if field == "session_idle_minutes":
        try:
            return int(value) >= 1
        except (TypeError, ValueError):
            return False
    if field == "session_max_hours":
        try:
            return int(value) >= 1
        except (TypeError, ValueError):
            return False
    return False


def _coerce_field(field: str, value: Any) -> Any:
    """Coerce a raw value to the correct Python type for a field.

    Args:
        field: Field name in AppSettings.
        value: Raw value (already validated).

    Returns:
        Coerced value suitable for the AppSettings constructor.
    """
    if field in ("session_idle_minutes", "session_max_hours"):
        return int(value)
    if field == "log_level":
        return str(value).lower()
    return value


class AppSettings(BaseModel):
    """Application configuration resolved from addon options, env vars, and defaults."""

    log_level: str = "info"
    db_path: str = "/data/captive_portal.db"
    session_idle_minutes: int = 30
    session_max_hours: int = 8

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

        for field_name in ("log_level", "db_path", "session_idle_minutes", "session_max_hours"):
            # --- Try addon option ---
            addon_key = next(
                (k for k, v in _ADDON_OPTION_MAP.items() if v == field_name),
                None,
            )
            if addon_key and addon_key in addon_options:
                raw = addon_options[addon_key]
                if _validate_field(field_name, raw):
                    resolved[field_name] = _coerce_field(field_name, raw)
                    continue
                # Invalid addon option → log warning and fall through
                logger.warning(
                    "Invalid addon option '%s': %r — ignoring, will try "
                    "environment variable or default.",
                    addon_key,
                    raw,
                )

            # --- Try environment variable ---
            env_key = next(
                (k for k, v in _ENV_VAR_MAP.items() if v == field_name),
                None,
            )
            if env_key:
                env_val = os.environ.get(env_key)
                if env_val is not None and _validate_field(field_name, env_val):
                    resolved[field_name] = _coerce_field(field_name, env_val)
                    continue

            # --- Fall through to built-in default ---
            resolved[field_name] = getattr(defaults, field_name)

        return cls(**resolved)

    def to_session_config(self) -> SessionConfig:
        """Convert session-related settings to a ``SessionConfig``.

        Returns:
            SessionConfig with idle_minutes and max_hours from these settings.
        """
        return SessionConfig(
            idle_minutes=self.session_idle_minutes,
            max_hours=self.session_max_hours,
        )

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
        log.info("  session_idle_minutes = %d", self.session_idle_minutes)
        log.info("  session_max_hours = %d", self.session_max_hours)

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
        if not parent.exists():
            msg = f"Database directory does not exist for db_path='{self.db_path}': {parent}"
            raise RuntimeError(msg)
        if not os.access(str(parent), os.W_OK):
            msg = f"Database directory is not writable for db_path='{self.db_path}': {parent}"
            raise RuntimeError(msg)
