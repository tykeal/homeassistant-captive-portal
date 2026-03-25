# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Retry queue service for controller operation failures."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Deque, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class OperationType(str, Enum):
    """Types of controller operations that can be retried."""

    AUTHORIZE = "authorize"
    REVOKE = "revoke"
    UPDATE = "update"


@dataclass
class RetryOperation:
    """Retry operation metadata.

    Attributes:
        operation_id: Unique identifier for this operation
        operation_type: Type of operation (authorize/revoke/update)
        mac_address: Target MAC address
        params: Additional operation parameters
        attempts: Number of retry attempts made
        next_retry_utc: Timestamp for next retry attempt
        created_utc: Original operation creation time
    """

    operation_id: UUID
    operation_type: OperationType
    mac_address: str
    params: dict[str, Any]
    attempts: int = 0
    next_retry_utc: Optional[datetime] = None
    created_utc: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0)
    )


class RetryQueueService:
    """Background retry queue for failed controller operations.

    Implements exponential backoff with maximum retry limits.
    Default: 3 retries with 2s, 4s, 8s delays.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 2.0,
        max_delay_seconds: float = 60.0,
    ) -> None:
        """Initialize retry queue service.

        Args:
            max_retries: Maximum retry attempts per operation
            base_delay_seconds: Initial delay before first retry
            max_delay_seconds: Maximum delay cap for exponential backoff
        """
        self._queue: Deque[RetryOperation] = deque()
        self._max_retries = max_retries
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._executor: Optional[Callable[[RetryOperation], Any]] = None

    def set_executor(self, executor: Callable[[RetryOperation], Any]) -> None:
        """Set the executor function for retry operations.

        Args:
            executor: Async function that executes a retry operation
        """
        self._executor = executor

    async def enqueue(self, operation: RetryOperation) -> None:
        """Add operation to retry queue.

        Args:
            operation: Retry operation to enqueue
        """
        # Calculate next retry time with exponential backoff
        # Pre-truncate to second precision for consistent scheduling with 1s processor intervals
        delay = min(self._base_delay * (2**operation.attempts), self._max_delay)
        operation.next_retry_utc = (datetime.now(timezone.utc) + timedelta(seconds=delay)).replace(
            microsecond=0
        )

        self._queue.append(operation)
        logger.info(
            f"Enqueued {operation.operation_type} for {operation.mac_address}, "
            f"attempt {operation.attempts + 1}/{self._max_retries}"
        )

    async def start(self) -> None:
        """Start background retry processor."""
        if self._running:
            logger.warning("Retry queue already running")
            return

        if self._executor is None:
            raise RuntimeError("Executor not set. Call set_executor() first.")

        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("Retry queue service started")

    async def stop(self) -> None:
        """Stop background retry processor."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Retry queue service stopped")

    async def _process_queue(self) -> None:
        """Process retry queue in background loop."""
        while self._running:
            await asyncio.sleep(1)  # Check queue every second

            if not self._queue:
                continue

            now_utc = datetime.now(timezone.utc)

            # Process all operations ready for retry
            processed = 0
            while self._queue and processed < len(self._queue):
                operation = self._queue.popleft()

                # Check if ready for retry
                if operation.next_retry_utc is None or operation.next_retry_utc > now_utc:
                    # Not ready yet, re-queue
                    self._queue.append(operation)
                    processed += 1
                    continue

                # Execute retry
                operation.attempts += 1
                try:
                    if self._executor:
                        await self._executor(operation)
                    logger.info(
                        f"Retry {operation.operation_type} succeeded for "
                        f"{operation.mac_address} on attempt {operation.attempts}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Retry {operation.operation_type} failed for {operation.mac_address}: {e}"
                    )

                    # Re-queue if under max retries
                    if operation.attempts < self._max_retries:
                        await self.enqueue(operation)
                    else:
                        logger.error(
                            f"Max retries ({self._max_retries}) exceeded for "
                            f"{operation.operation_type} on {operation.mac_address}"
                        )

                processed += 1

    def queue_size(self) -> int:
        """Get current queue size.

        Returns:
            Number of operations in queue
        """
        return len(self._queue)

    def is_running(self) -> bool:
        """Check if service is running.

        Returns:
            True if background processor is active
        """
        return self._running
