# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Rental Control event processing service."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from captive_portal.integrations.ha_client import HAClient
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.persistence.repositories import RentalControlEventRepository

logger = logging.getLogger(__name__)


class RentalControlService:
    """Service for processing Rental Control events from Home Assistant.

    Attributes:
        ha_client: HA REST API client
        event_repo: Event repository for persistence
    """

    def __init__(
        self,
        ha_client: HAClient,
        event_repo: RentalControlEventRepository,
    ) -> None:
        """Initialize rental control service.

        Args:
            ha_client: HA REST API client
            event_repo: Event repository
        """
        self.ha_client = ha_client
        self.event_repo = event_repo

    async def process_events(self) -> None:
        """Process all enabled integrations (called by poller).

        Raises:
            Exception: On HA API errors
        """
        # This will be implemented with integration config retrieval
        # For now, placeholder for poller compatibility
        pass

    async def process_single_event(
        self,
        integration_config: HAIntegrationConfig,
        event_index: int,
        event_data: Dict[str, Any],
    ) -> None:
        """Process a single Rental Control event.

        Args:
            integration_config: Integration configuration
            event_index: Event position (0-N)
            event_data: Event data from HA entity state

        Raises:
            ValueError: On missing required attributes
        """
        attributes = event_data.get("attributes", {})

        # Extract timestamps
        start_str = attributes.get("start")
        end_str = attributes.get("end")

        if not start_str or not end_str:
            logger.warning(
                "Skipping event with missing timestamps",
                extra={
                    "event_index": event_index,
                    "integration_id": integration_config.integration_id,
                },
            )
            return

        start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end_utc = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        # Note: Grace period NOT applied here - applied at grant creation time

        # Extract identifiers
        slot_name = attributes.get("slot_name")
        slot_code = attributes.get("slot_code")
        last_four = attributes.get("last_four")

        # Validate at least one identifier exists
        if not any([slot_name, slot_code, last_four]):
            logger.warning(
                "Skipping event with no valid identifiers",
                extra={
                    "event_index": event_index,
                    "integration_id": integration_config.integration_id,
                },
            )
            return

        # Create event record with booking window (grace applied at grant time)
        event = RentalControlEvent(
            integration_id=integration_config.id,
            event_index=event_index,
            slot_name=slot_name,
            slot_code=slot_code,
            last_four=last_four,
            start_utc=start_utc,
            end_utc=end_utc,  # Booking end without grace
            raw_attributes=json.dumps(attributes),
        )

        # Upsert event (update if exists, insert if new)
        await self.event_repo.upsert(event)

        logger.info(
            "Processed Rental Control event",
            extra={
                "integration_id": str(integration_config.integration_id),
                "event_index": event_index,
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
            },
        )

    def get_auth_identifier(
        self,
        event: RentalControlEvent,
        integration_config: HAIntegrationConfig,
    ) -> Optional[str]:
        """Get auth identifier from event using configured attribute with fallback.

        Args:
            event: Rental Control event
            integration_config: Integration configuration

        Returns:
            Auth identifier string or None if not available

        Fallback order:
            1. Configured auth_attribute
            2. slot_code (if not configured attribute)
            3. slot_name (if slot_code empty)
        """
        # Try configured attribute first
        attr_name = integration_config.identifier_attr.value
        identifier: Optional[str] = getattr(event, attr_name, None)

        if identifier:
            return identifier

        # Fallback logic
        if integration_config.identifier_attr != IdentifierAttr.SLOT_CODE:
            if event.slot_code:
                return event.slot_code

        if event.slot_name:
            return event.slot_name

        return None
