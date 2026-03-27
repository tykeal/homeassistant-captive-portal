# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant calendar discovery service models and logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, computed_field
from sqlmodel import Session, select

from captive_portal.integrations.ha_errors import (
    HAAuthenticationError,
    HAConnectionError,
    HADiscoveryError,
    HAServerError,
    HATimeoutError,
)
from captive_portal.models.ha_integration_config import HAIntegrationConfig

if TYPE_CHECKING:
    from captive_portal.integrations.ha_client import HAClient

_STATE_DISPLAY_MAP: dict[str, str] = {
    "on": "Active booking",
    "off": "No active bookings",
    "unavailable": "Unavailable",
}


class DiscoveredIntegration(BaseModel):
    """A calendar entity discovered from Home Assistant."""

    entity_id: str
    friendly_name: str
    state: str
    event_summary: Optional[str] = None
    event_start: Optional[str] = None
    event_end: Optional[str] = None
    already_configured: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state_display(self) -> str:
        """Human-readable display string derived from entity state."""
        return _STATE_DISPLAY_MAP.get(self.state, self.state)


class DiscoveryResult(BaseModel):
    """Wrapper for a calendar discovery operation result."""

    available: bool
    integrations: list[DiscoveredIntegration] = []
    error_message: Optional[str] = None
    error_category: Optional[str] = None


logger = logging.getLogger("captive_portal")

_RENTAL_CONTROL_PREFIX = "calendar.rental_control_"

_ERROR_CATEGORY_MAP: dict[type, str] = {
    HAConnectionError: "connection",
    HAAuthenticationError: "auth",
    HATimeoutError: "timeout",
    HAServerError: "server_error",
}


class HADiscoveryService:
    """Service that discovers Rental Control calendar entities from HA.

    Attributes:
        ha_client: HAClient instance for API communication.
        session: SQLModel database session for config lookups.
    """

    def __init__(self, ha_client: HAClient, session: Session) -> None:
        """Initialize the discovery service.

        Args:
            ha_client: HAClient instance for HA API calls.
            session: SQLModel database session.
        """
        self.ha_client = ha_client
        self.session = session

    async def discover(self) -> DiscoveryResult:
        """Discover Rental Control calendar entities from Home Assistant.

        Calls get_all_states(), filters for calendar.rental_control_* entities,
        cross-references existing HAIntegrationConfig rows, and maps to
        DiscoveredIntegration models.

        Returns:
            DiscoveryResult with available=True on success, or
            available=False with error details on failure.
        """
        try:
            all_states = await self.ha_client.get_all_states()
        except HADiscoveryError as exc:
            category = _ERROR_CATEGORY_MAP.get(type(exc), "unknown")
            logger.error(
                "HA discovery failed (%s): %s | detail: %s",
                category,
                exc.user_message,
                exc.detail,
            )
            return DiscoveryResult(
                available=False,
                error_message=str(exc),
                error_category=category,
            )

        # Filter for Rental Control calendar entities
        rental_entities = [
            entity
            for entity in all_states
            if entity.get("entity_id", "").startswith(_RENTAL_CONTROL_PREFIX)
        ]

        # Look up already-configured integration IDs
        configured_ids: set[str] = set()
        statement = select(HAIntegrationConfig.integration_id)
        results = self.session.exec(statement)
        for row in results:
            configured_ids.add(row)

        # Map to DiscoveredIntegration models
        integrations: list[DiscoveredIntegration] = []
        for entity in rental_entities:
            attrs = entity.get("attributes", {})
            integrations.append(
                DiscoveredIntegration(
                    entity_id=entity["entity_id"],
                    friendly_name=attrs.get("friendly_name", entity["entity_id"]),
                    state=entity.get("state", "unknown"),
                    event_summary=attrs.get("message"),
                    event_start=attrs.get("start_time"),
                    event_end=attrs.get("end_time"),
                    already_configured=entity["entity_id"] in configured_ids,
                )
            )

        return DiscoveryResult(
            available=True,
            integrations=integrations,
        )
