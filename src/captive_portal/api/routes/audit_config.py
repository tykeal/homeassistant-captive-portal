# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""API routes for audit configuration management."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from captive_portal.models.audit_config import AuditConfig
from captive_portal.security.session_middleware import require_admin

router = APIRouter(prefix="/api/v1/admin/audit", tags=["admin", "audit"])

# In-memory storage for MVP (future: database)
_audit_config = AuditConfig()


@router.get("/config", response_model=AuditConfig)
async def get_audit_config(
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> AuditConfig:
    """Get current audit log retention configuration.

    Args:
        admin_id: Authenticated admin user ID (from dependency)

    Returns:
        Current audit configuration
    """
    return _audit_config


@router.put("/config", response_model=AuditConfig)
async def update_audit_config(
    config: AuditConfig,
    admin_id: Annotated[UUID, Depends(require_admin)],
) -> AuditConfig:
    """Update audit log retention configuration.

    Args:
        config: New audit configuration
        admin_id: Authenticated admin user ID (from dependency)

    Returns:
        Updated audit configuration
    """
    global _audit_config
    _audit_config = config
    return _audit_config
