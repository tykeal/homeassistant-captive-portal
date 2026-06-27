# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Shared primitive settings validators."""

from __future__ import annotations

from typing import Any


def validate_bool_like(value: Any) -> bool:
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


def validate_non_empty_str(value: Any) -> bool:
    """Check if *value* is a non-empty stripped string.

    Args:
        value: Candidate value.

    Returns:
        True if the value is a non-empty string after stripping.
    """
    return isinstance(value, str) and len(value.strip()) > 0
