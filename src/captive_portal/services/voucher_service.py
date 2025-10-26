# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Voucher service for creation, validation, and redemption logic."""

import asyncio
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)


class VoucherCollisionError(Exception):
    """Raised when voucher code generation exhausts retry attempts."""

    pass


class VoucherRedemptionError(Exception):
    """Raised when voucher cannot be redeemed (expired, revoked, etc.)."""

    pass


class VoucherService:
    """Service for voucher lifecycle operations."""

    def __init__(
        self,
        session: Session,
        voucher_repo: Optional[VoucherRepository] = None,
        grant_repo: Optional[AccessGrantRepository] = None,
    ):
        """Initialize voucher service.

        Args:
            session: Database session
            voucher_repo: Optional voucher repository (creates if None)
            grant_repo: Optional grant repository (creates if None)
        """
        self.session = session
        self.voucher_repo = voucher_repo or VoucherRepository(session)
        self.grant_repo = grant_repo or AccessGrantRepository(session)

    def _generate_code(self, length: int = 10) -> str:
        """Generate random voucher code (A-Z0-9).

        Args:
            length: Code length (4-24, default 10)

        Returns:
            Random uppercase alphanumeric code
        """
        if not 4 <= length <= 24:
            raise ValueError("Voucher code length must be 4-24 characters")
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def create(
        self,
        duration_minutes: int,
        booking_ref: Optional[str] = None,
        up_kbps: Optional[int] = None,
        down_kbps: Optional[int] = None,
        code_length: int = 10,
        max_retries: int = 5,
    ) -> Voucher:
        """Create voucher with collision retry logic (D3 decision).

        Implements exponential backoff: 50ms, 100ms, 200ms, 400ms, 800ms per
        phase1.md specification.

        Args:
            duration_minutes: Grant duration (>0)
            booking_ref: Optional booking reference (case-sensitive)
            up_kbps: Optional upload bandwidth limit (>0)
            down_kbps: Optional download bandwidth limit (>0)
            code_length: Code length (4-24, default 10)
            max_retries: Max collision retry attempts (default 5)

        Returns:
            Created voucher with generated code

        Raises:
            VoucherCollisionError: If max retries exhausted
            ValueError: If invalid parameters
        """
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be > 0")

        backoff_ms = [50, 100, 200, 400, 800]  # Exponential backoff per spec

        for attempt in range(max_retries):
            try:
                code = self._generate_code(code_length)
                voucher = Voucher(
                    code=code,
                    duration_minutes=duration_minutes,
                    booking_ref=booking_ref,
                    up_kbps=up_kbps,
                    down_kbps=down_kbps,
                    status=VoucherStatus.UNUSED,
                    redeemed_count=0,
                )
                self.voucher_repo.add(voucher)
                self.voucher_repo.commit()
                return voucher
            except IntegrityError:
                # PK collision - code already exists
                self.voucher_repo.rollback()
                if attempt < max_retries - 1:
                    # Retry with backoff
                    await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                else:
                    # Exhausted retries
                    raise VoucherCollisionError(
                        f"Failed to generate unique voucher code after {max_retries} attempts"
                    )

        # Unreachable, but satisfy type checker
        raise VoucherCollisionError("Unexpected code path")

    async def redeem(
        self, code: str, mac: str, current_time: Optional[datetime] = None
    ) -> AccessGrant:
        """Redeem voucher for network access grant.

        Args:
            code: Voucher code (A-Z0-9)
            mac: Device MAC address
            current_time: Optional current time (defaults to now UTC)

        Returns:
            Created access grant

        Raises:
            VoucherRedemptionError: If voucher invalid/expired/revoked
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Retrieve voucher
        voucher = self.voucher_repo.get_by_code(code)
        if not voucher:
            raise VoucherRedemptionError(f"Voucher code '{code}' not found")

        # Validate status
        if voucher.status == VoucherStatus.REVOKED:
            raise VoucherRedemptionError(f"Voucher '{code}' has been revoked")

        # Check expiration
        if voucher.expires_utc < current_time:
            raise VoucherRedemptionError(f"Voucher '{code}' expired at {voucher.expires_utc}")

        # Check for duplicate redemption (same voucher + MAC)
        existing_grants = self.grant_repo.find_active_by_mac(mac)
        for grant in existing_grants:
            if grant.voucher_code == code:
                raise VoucherRedemptionError(f"Voucher '{code}' already redeemed for MAC '{mac}'")

        # Create access grant
        grant_start = current_time.replace(second=0, microsecond=0)  # Floor to minute
        grant_end = grant_start + timedelta(minutes=voucher.duration_minutes)
        # Ceil to next minute if needed
        if grant_end.second > 0 or grant_end.microsecond > 0:
            grant_end = grant_end.replace(second=0, microsecond=0) + timedelta(minutes=1)

        grant = AccessGrant(
            voucher_code=code,
            booking_ref=voucher.booking_ref,
            mac=mac,
            start_utc=grant_start,
            end_utc=grant_end,
            status=GrantStatus.PENDING,  # Will transition to ACTIVE after controller
        )

        # Update voucher state
        voucher.redeemed_count += 1
        voucher.last_redeemed_utc = current_time
        if voucher.status == VoucherStatus.UNUSED:
            voucher.status = VoucherStatus.ACTIVE

        # Persist changes
        self.grant_repo.add(grant)
        self.voucher_repo.commit()  # Commits both voucher update and grant insert

        return grant
