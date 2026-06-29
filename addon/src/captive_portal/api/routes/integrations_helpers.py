# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Helper logic for Home Assistant integration admin routes."""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional, cast
from uuid import UUID

from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from captive_portal.api.routes.admin_redirects import safe_admin_redirect
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)
from captive_portal.services.audit_service import AuditService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationSaveData:
    """Validated form data for saving an HA integration."""

    integration_id: str
    identifier_attr: IdentifierAttr
    checkout_grace_minutes: int
    allowed_vlans: list[int] | None


def integrations_redirect(root: str, key: str, message: str) -> RedirectResponse:
    """Build a redirect back to the integrations page.

    Args:
        root: ASGI root path prefix.
        key: Query parameter key (``success`` or ``error``).
        message: User-facing message.

    Returns:
        303 redirect response.
    """
    encoded_message = urllib.parse.quote_plus(message)
    return safe_admin_redirect(root, f"/admin/integrations/?{key}={encoded_message}")


def parse_allowed_vlans(
    allowed_vlans: Optional[str],
    root: str,
) -> list[int] | RedirectResponse | None:
    """Parse an optional comma-separated VLAN list.

    Args:
        allowed_vlans: Raw form field.
        root: ASGI root path prefix.

    Returns:
        Parsed VLAN list, ``None`` for empty input, or redirect on error.
    """
    if not allowed_vlans or not allowed_vlans.strip():
        return None

    try:
        parsed_vlans = sorted(set(int(v.strip()) for v in allowed_vlans.split(",") if v.strip()))
        for vid in parsed_vlans:
            if vid < 1 or vid > 4094:
                raise ValueError(f"Invalid VLAN ID: {vid}")
        return parsed_vlans
    except ValueError as exc:
        return integrations_redirect(root, "error", f"Invalid VLAN input: {exc}")


async def update_integration_record(
    session: Session,
    audit_service: AuditService,
    admin_id: UUID,
    integration: HAIntegrationConfig,
    data: IntegrationSaveData,
) -> None:
    """Persist updates to an existing integration.

    Args:
        session: Database session.
        audit_service: Audit logger.
        admin_id: Authenticated admin ID.
        integration: Existing integration record.
        data: Validated form data.
    """
    old_vlans = list(integration.allowed_vlans or [])
    integration.integration_id = data.integration_id
    integration.identifier_attr = data.identifier_attr
    integration.checkout_grace_minutes = data.checkout_grace_minutes
    integration.allowed_vlans = data.allowed_vlans

    session.add(integration)
    session.commit()

    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="update_integration",
        target_type="ha_integration_config",
        target_id=str(integration.id),
        metadata={
            "integration_id": data.integration_id,
            "allowed_vlans_old": old_vlans,
            "allowed_vlans_new": list(data.allowed_vlans or []),
        },
    )


async def create_integration_record(
    session: Session,
    audit_service: AuditService,
    admin_id: UUID,
    data: IntegrationSaveData,
    root: str,
) -> RedirectResponse | None:
    """Persist a new integration unless the identifier already exists.

    Args:
        session: Database session.
        audit_service: Audit logger.
        admin_id: Authenticated admin ID.
        data: Validated form data.
        root: ASGI root path prefix.

    Returns:
        Redirect response for duplicate integrations, otherwise ``None``.
    """
    dup_stmt: Any = select(HAIntegrationConfig).where(
        HAIntegrationConfig.integration_id == data.integration_id
    )
    existing: HAIntegrationConfig | None = cast(
        Optional[HAIntegrationConfig], session.exec(dup_stmt).first()
    )
    if existing:
        logger.warning("Duplicate integration: %s", data.integration_id)
        return integrations_redirect(root, "error", "Integration already exists")

    integration = HAIntegrationConfig(
        integration_id=data.integration_id,
        identifier_attr=data.identifier_attr,
        checkout_grace_minutes=data.checkout_grace_minutes,
        allowed_vlans=data.allowed_vlans,
    )

    session.add(integration)
    session.commit()
    session.refresh(integration)

    await audit_service.log_admin_action(
        admin_id=admin_id,
        action="create_integration",
        target_type="ha_integration_config",
        target_id=str(integration.id),
    )
    return None
