# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant polling service for Rental Control events."""

import asyncio
import logging
from typing import Optional

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.rental_control_service import RentalControlService

logger = logging.getLogger(__name__)


class HAPoller:
    """Background service that polls HA for Rental Control updates.

    Attributes:
        ha_client: HA REST API client
        rental_service: Service for processing rental events
        interval_seconds: Normal polling interval (default 60s)
        max_backoff_seconds: Maximum backoff interval (default 300s)
        _running: Flag indicating if poller is active
        _task: Background task handle
        _error_count: Consecutive error counter for backoff
    """

    def __init__(
        self,
        ha_client: HAClient,
        rental_service: RentalControlService,
        interval_seconds: float = 60,
        max_backoff_seconds: float = 300,
    ) -> None:
        """Initialize HA poller.

        Args:
            ha_client: HA REST API client
            rental_service: Service for processing rental events
            interval_seconds: Normal polling interval
            max_backoff_seconds: Maximum backoff interval
        """
        self.ha_client = ha_client
        self.rental_service = rental_service
        self.interval_seconds = interval_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._error_count = 0

    async def start(self) -> None:
        """Start polling loop."""
        self._running = True
        logger.info(
            "Starting HA poller",
            extra={
                "interval_seconds": self.interval_seconds,
                "max_backoff_seconds": self.max_backoff_seconds,
            },
        )

        while self._running:
            try:
                await self.rental_service.process_events()
                self._error_count = 0  # Reset on success
                await asyncio.sleep(self.interval_seconds)

            except Exception as exc:
                self._error_count += 1
                backoff = min(
                    self.interval_seconds * (2 ** (self._error_count - 1)),
                    self.max_backoff_seconds,
                )

                logger.error(
                    "HA polling error",
                    extra={
                        "error": str(exc),
                        "error_count": self._error_count,
                        "backoff_seconds": backoff,
                    },
                    exc_info=True,
                )

                await asyncio.sleep(backoff)

    async def stop(self) -> None:
        """Stop polling loop gracefully."""
        logger.info("Stopping HA poller")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
