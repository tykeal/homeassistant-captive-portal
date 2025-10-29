# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""RBAC matrix data (FR-017).
Minimal placeholder consumed by future middleware. Tests will import ROLE_ACTIONS.
"""

from __future__ import annotations
from typing import Dict, Set

# Stable role names
ROLES: Set[str] = {"viewer", "operator", "auditor", "admin"}

# Action -> roles allowed
ROLE_ACTIONS: Dict[str, Set[str]] = {
    "internal.health.read": {"viewer", "operator", "auditor", "admin"},
    # grant / voucher admins (placeholder endpoints to be wired later)
    "grants.list": {"operator", "auditor", "admin"},
    "grants.extend": {"operator", "admin"},
    "grants.revoke": {"operator", "admin"},
    "vouchers.redeem": {"operator", "admin"},
    "vouchers.create": {"operator", "admin"},
    "admin.accounts.create": {"admin"},
    "admin.accounts.list": {"admin"},
    "audit.entries.list": {"auditor", "admin"},
    "config.theming.update": {"admin"},
}


def is_allowed(role: str, action: str) -> bool:
    """Check if role is allowed to perform action.

    Args:
        role: User role (e.g., 'admin', 'operator')
        action: Action identifier (e.g., 'grants.list')

    Returns:
        True if role has permission for action
    """
    return role in ROLE_ACTIONS.get(action, set())
