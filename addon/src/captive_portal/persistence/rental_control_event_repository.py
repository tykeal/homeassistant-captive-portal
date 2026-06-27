# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Rental control event repository implementation."""

from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy import delete as sa_delete
from sqlmodel import select

from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.persistence.repository_base import BaseRepository


class RentalControlEventRepository(BaseRepository[RentalControlEvent]):
    """Repository for RentalControlEvent entities."""

    def get_model_class(self) -> type[RentalControlEvent]:
        """Return RentalControlEvent model class."""
        return RentalControlEvent

    def get_by_id(self, event_id: int) -> Optional[RentalControlEvent]:
        """Retrieve event by ID.

        Args:
            event_id: Event ID.

        Returns:
            RentalControlEvent instance or None.
        """
        return cast(Optional[RentalControlEvent], self.session.get(RentalControlEvent, event_id))

    async def upsert(self, event: RentalControlEvent) -> RentalControlEvent:
        """Insert or update event record.

        Updates existing event based on the (integration_id,
        event_index) unique constraint.

        Args:
            event: Event to insert/update.

        Returns:
            Updated event instance.
        """
        statement: Any = select(RentalControlEvent).where(
            RentalControlEvent.integration_id == event.integration_id,
            RentalControlEvent.event_index == event.event_index,
        )
        existing: RentalControlEvent | None = self.session.exec(statement).first()

        if existing:
            existing.slot_name = event.slot_name
            existing.slot_code = event.slot_code
            existing.last_four = event.last_four
            existing.start_utc = event.start_utc
            existing.end_utc = event.end_utc
            existing.raw_attributes = event.raw_attributes
            existing.updated_utc = datetime.now(timezone.utc)
            self.session.add(existing)
            self.session.flush()
            self.session.refresh(existing)
            return existing
        return self.add(event)

    async def delete_events_older_than(self, cutoff_date: datetime) -> int:
        """Delete events with end_utc older than cutoff date.

        Args:
            cutoff_date: Cutoff timestamp (UTC).

        Returns:
            Number of deleted events.
        """
        cutoff_naive = (
            cutoff_date.astimezone(timezone.utc).replace(tzinfo=None)
            if cutoff_date.tzinfo
            else cutoff_date
        )
        statement = sa_delete(RentalControlEvent).where(
            RentalControlEvent.end_utc < cutoff_naive  # type: ignore[arg-type]
        )
        result: Any = self.session.execute(statement.execution_options(synchronize_session=False))
        self.session.flush()
        return int(result.rowcount or 0)
