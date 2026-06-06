# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for RentalControlEventRepository cleanup helpers."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.persistence.repositories import RentalControlEventRepository


def _make_event(
    session: Session,
    *,
    event_index: int,
    end_utc: datetime,
) -> RentalControlEvent:
    """Create and persist a Rental Control event for repository tests."""
    event = RentalControlEvent(
        integration_id="calendar.rental_control_test",
        event_index=event_index,
        slot_code=f"CODE{event_index}",
        slot_name=f"Guest {event_index}",
        last_four=f"{event_index:04d}"[-4:],
        start_utc=end_utc - timedelta(days=1),
        end_utc=end_utc,
        raw_attributes="{}",
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_delete_events_older_than_removes_matching_rows(db_session: Session) -> None:
    """Deleting stale events removes only rows older than the cutoff."""
    now = datetime.now(timezone.utc)
    stale_event = _make_event(
        db_session,
        event_index=0,
        end_utc=now - timedelta(days=2),
    )
    stale_event_id = stale_event.id
    recent_event = _make_event(
        db_session,
        event_index=1,
        end_utc=now - timedelta(hours=12),
    )
    recent_event_id = recent_event.id
    repo = RentalControlEventRepository(db_session)

    deleted_count = await repo.delete_events_older_than(now - timedelta(days=1))
    db_session.commit()

    assert deleted_count == 1
    remaining_ids = {event.id for event in db_session.exec(select(RentalControlEvent)).all()}
    assert stale_event_id not in remaining_ids
    assert recent_event_id in remaining_ids


@pytest.mark.asyncio
async def test_delete_events_older_than_returns_zero_when_nothing_matches(
    db_session: Session,
) -> None:
    """Deleting with no stale rows returns zero and keeps existing events."""
    now = datetime.now(timezone.utc)
    recent_event = _make_event(
        db_session,
        event_index=0,
        end_utc=now - timedelta(hours=12),
    )
    recent_event_id = recent_event.id
    repo = RentalControlEventRepository(db_session)

    deleted_count = await repo.delete_events_older_than(now - timedelta(days=1))
    db_session.commit()

    assert deleted_count == 0
    remaining_ids = {event.id for event in db_session.exec(select(RentalControlEvent)).all()}
    assert remaining_ids == {recent_event_id}
