# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""API routes for audit configuration management."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from captive_portal.models.audit_config import AuditConfig
from captive_portal.security.session_middleware import require_admin

router = APIRouter(prefix="/api/admin/audit", tags=["admin", "audit"])


def _get_audit_config(request: Request) -> AuditConfig:
    """Get audit config from app state, initializing if needed."""
    if not hasattr(request.app.state, "audit_config"):
        request.app.state.audit_config = AuditConfig()
    config: AuditConfig = request.app.state.audit_config
    return config


@router.get("/config", response_model=AuditConfig)
async def get_audit_config(
    admin_id: Annotated[UUID, Depends(require_admin)],
    config: Annotated[AuditConfig, Depends(_get_audit_config)],
) -> AuditConfig:
    """Get current audit log retention configuration.

    Args:
        admin_id: Authenticated admin user ID (from dependency)
        config: Current audit configuration from app state

    Returns:
        Current audit configuration
    """
    return config


@router.put("/config", response_model=AuditConfig)
async def update_audit_config(
    config: AuditConfig,
    admin_id: Annotated[UUID, Depends(require_admin)],
    request: Request,
) -> AuditConfig:
    """Update audit log retention configuration.

    Note: Configuration is stored in-memory (app.state) for MVP.
    Changes will reset to defaults on application restart.
    Database persistence is planned for a future release.

    Args:
        config: New audit configuration
        admin_id: Authenticated admin user ID (from dependency)
        request: FastAPI request for app state access

    Returns:
        Updated audit configuration
    """
    request.app.state.audit_config = config
    return config
