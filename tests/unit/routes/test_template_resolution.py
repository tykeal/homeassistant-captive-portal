# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test template path resolution in route modules.

Validates that _TEMPLATES_DIR variables resolve to existing directories
containing expected template subdirectories regardless of working directory.
"""

from pathlib import Path


def test_guest_portal_templates_dir_exists() -> None:
    """guest_portal.py _TEMPLATES_DIR should resolve to existing dir."""
    from captive_portal.api.routes.guest_portal import _TEMPLATES_DIR

    templates_dir = Path(_TEMPLATES_DIR)
    assert templates_dir.is_dir(), f"Templates dir not found: {templates_dir}"
    assert (templates_dir / "guest").is_dir(), "guest/ subdirectory missing"


def test_portal_settings_ui_templates_dir_exists() -> None:
    """portal_settings_ui.py _TEMPLATES_DIR should resolve to existing dir."""
    from captive_portal.api.routes.portal_settings_ui import _TEMPLATES_DIR

    templates_dir = Path(_TEMPLATES_DIR)
    assert templates_dir.is_dir(), f"Templates dir not found: {templates_dir}"
    assert (templates_dir / "admin").is_dir(), "admin/ subdirectory missing"


def test_integrations_ui_templates_dir_exists() -> None:
    """integrations_ui.py _TEMPLATES_DIR should resolve to existing dir."""
    from captive_portal.api.routes.integrations_ui import _TEMPLATES_DIR

    templates_dir = Path(_TEMPLATES_DIR)
    assert templates_dir.is_dir(), f"Templates dir not found: {templates_dir}"
    assert (templates_dir / "admin").is_dir(), "admin/ subdirectory missing"


def test_templates_dir_contains_portal_subdirectory() -> None:
    """Templates dir should contain portal/ subdirectory."""
    from captive_portal.api.routes.guest_portal import _TEMPLATES_DIR

    templates_dir = Path(_TEMPLATES_DIR)
    assert (templates_dir / "portal").is_dir(), "portal/ subdirectory missing"
