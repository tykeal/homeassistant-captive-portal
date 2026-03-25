# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Application configuration module.

Provides ``AppSettings`` — a pydantic model that loads configuration from
Home Assistant addon options, environment variables, and built-in defaults
with a per-field three-tier precedence chain.
"""

from captive_portal.config.settings import AppSettings

__all__ = ["AppSettings"]
