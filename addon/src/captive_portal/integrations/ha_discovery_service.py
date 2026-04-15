# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant calendar discovery service models and logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

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

_RENTAL_CONTROL_PLATFORM = "rental_control"
_RENTAL_CONTROL_FRIENDLY_PREFIX = "Rental Control"

_ERROR_CATEGORY_MAP: dict[type, str] = {
    HAConnectionError: "connection",
    HAAuthenticationError: "auth",
    HATimeoutError: "timeout",
    HAServerError: "server_error",
}


def _is_rental_control_calendar(entity: dict[str, Any]) -> bool:
    """Check whether an entity state dict looks like a Rental Control calendar.

    Used as the fallback when the entity registry API is unavailable.
    Matches calendar entities whose ``entity_id`` contains
    ``rental_control`` or whose ``friendly_name`` starts with
    ``"Rental Control"``.

    Args:
        entity: Entity state dict from ``/api/states``.

    Returns:
        ``True`` if the entity is likely a Rental Control calendar.
    """
    entity_id = entity.get("entity_id", "")
    if not entity_id.startswith("calendar."):
        return False
    if _RENTAL_CONTROL_PLATFORM in entity_id:
        return True
    friendly = entity.get("attributes", {}).get("friendly_name", "")
    if isinstance(friendly, str) and friendly.startswith(
        _RENTAL_CONTROL_FRIENDLY_PREFIX,
    ):
        return True
    return False


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

        Queries the entity registry for entities created by the
        ``rental_control`` platform, then fetches full state objects
        for the matching calendar entities.  Falls back to
        attribute-based matching when the entity registry is
        unavailable (e.g. HA Supervisor proxy, older HA versions).

        The fallback matches calendar entities whose ``entity_id``
        contains ``rental_control`` or whose ``friendly_name``
        starts with ``"Rental Control"``.

        Returns:
            DiscoveryResult with available=True on success, or
            available=False with error details on failure.
        """
        # Attempt platform-based discovery via entity registry
        registry_entity_ids: set[str] | None = None
        try:
            registry = await self.ha_client.get_entity_registry()
            registry_entity_ids = {
                entry["entity_id"]
                for entry in registry
                if entry.get("platform") == _RENTAL_CONTROL_PLATFORM
                and entry.get("entity_id", "").startswith("calendar.")
            }
        except Exception:
            logger.warning(
                "Entity registry unavailable, falling back to attribute-based discovery",
            )

        try:
            all_states = await self.ha_client.get_all_states()
        except HADiscoveryError as exc:
            category = _ERROR_CATEGORY_MAP.get(type(exc), "unknown")
            logger.error(
                "HA discovery failed: category=%s message=%s detail=%s",
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
        if registry_entity_ids is not None:
            rental_entities = [
                entity
                for entity in all_states
                if entity.get("entity_id", "") in registry_entity_ids
            ]
        else:
            rental_entities = [
                entity for entity in all_states if _is_rental_control_calendar(entity)
            ]

        logger.info(
            "HA discovery: total_entities=%d rental_entities=%d",
            len(all_states),
            len(rental_entities),
        )

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
            raw_friendly_name = attrs.get("friendly_name")
            if isinstance(raw_friendly_name, str) and raw_friendly_name.strip():
                friendly_name = raw_friendly_name
            else:
                friendly_name = entity["entity_id"]

            integrations.append(
                DiscoveredIntegration(
                    entity_id=entity["entity_id"],
                    friendly_name=friendly_name,
                    state=entity.get("state", "unknown"),
                    event_summary=attrs.get("message"),
                    event_start=attrs.get("start_time"),
                    event_end=attrs.get("end_time"),
                    already_configured=entity["entity_id"] in configured_ids,
                )
            )

        logger.debug(
            "HA discovery complete: discovered=%d configured=%d",
            len(integrations),
            len(configured_ids),
        )

        return DiscoveryResult(
            available=True,
            integrations=integrations,
        )
