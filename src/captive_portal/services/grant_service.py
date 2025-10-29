# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Grant service for access grant lifecycle management."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.utils.time_utils import ceil_to_minute


class GrantNotFoundError(Exception):
    """Raised when grant ID not found."""

    pass


class GrantOperationError(Exception):
    """Raised when grant operation fails (e.g., revoke on revoked grant)."""

    pass


class GrantService:
    """Service for access grant lifecycle operations."""

    def __init__(
        self,
        session: Session,
        grant_repo: Optional[AccessGrantRepository] = None,
    ):
        """Initialize grant service.

        Args:
            session: Database session
            grant_repo: Optional grant repository (creates if None)
        """
        self.session = session
        self.grant_repo = grant_repo or AccessGrantRepository(session)

    async def create(
        self,
        mac: str,
        start_utc: datetime,
        end_utc: datetime,
        voucher_code: Optional[str] = None,
        booking_ref: Optional[str] = None,
        session_token: Optional[str] = None,
    ) -> AccessGrant:
        """Create access grant with timestamp rounding.

        Args:
            mac: Device MAC address (required)
            start_utc: Grant start time (will be floored to minute)
            end_utc: Grant end time (will be ceiled to minute)
            voucher_code: Optional voucher code FK
            booking_ref: Optional booking reference (case-sensitive)
            session_token: Optional session token (when voucher_code is None)

        Returns:
            Created access grant with PENDING status

        Raises:
            ValueError: If MAC is empty or times are invalid
        """
        if not mac or not mac.strip():
            raise ValueError("MAC address is required")

        if end_utc <= start_utc:
            raise ValueError("end_utc must be after start_utc")

        # AccessGrant __init__ handles timestamp rounding automatically
        grant = AccessGrant(
            voucher_code=voucher_code,
            booking_ref=booking_ref,
            mac=mac,
            session_token=session_token,
            start_utc=start_utc,
            end_utc=end_utc,
            status=GrantStatus.PENDING,
        )

        self.grant_repo.add(grant)
        self.grant_repo.commit()
        return grant

    async def extend(
        self,
        grant_id: UUID,
        additional_minutes: int,
        current_time: Optional[datetime] = None,
    ) -> AccessGrant:
        """Extend grant duration by adding minutes to end_utc.

        Args:
            grant_id: Grant UUID
            additional_minutes: Minutes to add to end_utc (>0)
            current_time: Optional current time (defaults to now UTC)

        Returns:
            Updated grant with extended end_utc (ceiled to minute)

        Raises:
            GrantNotFoundError: If grant_id not found
            GrantOperationError: If grant is revoked (cannot extend revoked)
            ValueError: If additional_minutes <= 0
        """
        if additional_minutes <= 0:
            raise ValueError("additional_minutes must be > 0")

        if current_time is None:
            current_time = datetime.now(timezone.utc)

        grant = self.grant_repo.get_by_id(grant_id)
        if not grant:
            raise GrantNotFoundError(f"Grant {grant_id} not found")

        if grant.status == GrantStatus.REVOKED:
            raise GrantOperationError(f"Cannot extend revoked grant {grant_id}")

        # Extend end_utc and ceil to next minute
        new_end = grant.end_utc + timedelta(minutes=additional_minutes)
        grant.end_utc = ceil_to_minute(new_end)
        grant.updated_utc = current_time

        # Reactivate expired grant if being extended
        if grant.status == GrantStatus.EXPIRED:
            grant.status = GrantStatus.ACTIVE

        self.grant_repo.commit()
        return grant

    async def revoke(
        self,
        grant_id: UUID,
        current_time: Optional[datetime] = None,
    ) -> AccessGrant:
        """Revoke access grant (idempotent).

        Args:
            grant_id: Grant UUID
            current_time: Optional current time (defaults to now UTC)

        Returns:
            Updated grant with REVOKED status and end_utc set to current time
            (truncated to second precision)

        Raises:
            GrantNotFoundError: If grant_id not found
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        grant = self.grant_repo.get_by_id(grant_id)
        if not grant:
            raise GrantNotFoundError(f"Grant {grant_id} not found")

        # Idempotent - revoke already-revoked grant is no-op
        if grant.status == GrantStatus.REVOKED:
            return grant

        # Revoke grant: set status and end time to current time
        grant.status = GrantStatus.REVOKED
        grant.end_utc = current_time.replace(microsecond=0)
        grant.updated_utc = current_time

        self.grant_repo.commit()
        return grant
