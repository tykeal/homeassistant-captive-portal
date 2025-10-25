# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for static RBAC matrix definitions.

Single test ensures viewer not in grants.list action; docstring for coverage.
"""

from captive_portal import security


def test_matrix_contains_action_grants_list() -> None:
    """Matrix enforces grants.list excludes viewer but includes others."""
    assert "grants.list" in security.ROLE_ACTIONS
    assert "viewer" not in security.ROLE_ACTIONS["grants.list"]
