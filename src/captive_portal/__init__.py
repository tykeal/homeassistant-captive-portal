# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Captive Portal application package."""
# Lazy import to avoid circular dependency during test collection

def create_app():
    from .app import create_app as _factory
    return _factory()

try:  # pragma: no cover
    from .app import create_app as _factory
    app = _factory()
except Exception:  # pragma: no cover
    app = None
