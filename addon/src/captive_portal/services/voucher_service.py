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
from captive_portal.utils.time_utils import ceil_to_minute, floor_to_minute


class VoucherCollisionError(Exception):
    """Raised when voucher code generation exhausts retry attempts."""

    pass


class VoucherRedemptionError(Exception):
    """Raised when voucher cannot be redeemed (expired, revoked, etc.)."""

    pass


class VoucherDeviceLimitError(VoucherRedemptionError):
    """Raised when voucher has reached max device limit."""

    pass


class VoucherNotFoundError(Exception):
    """Raised when a voucher code cannot be found."""

    def __init__(self, code: str) -> None:
        """Initialize with the missing voucher code."""
        self.code = code
        super().__init__(code)


class VoucherExpiredError(Exception):
    """Raised when an operation targets an expired voucher."""

    def __init__(self, code: str) -> None:
        """Initialize with the expired voucher code."""
        self.code = code
        super().__init__(code)


class VoucherRedeemedError(Exception):
    """Raised when an operation is disallowed because the voucher was redeemed."""

    def __init__(self, code: str) -> None:
        """Initialize with the redeemed voucher code."""
        self.code = code
        super().__init__(code)


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

    def expire_stale_vouchers(
        self,
        vouchers: list[Voucher],
        current_time: datetime | None = None,
    ) -> int:
        """Transition ACTIVE vouchers past expiry to EXPIRED.

        Iterates *vouchers* and sets ``status = EXPIRED`` for each
        entry whose expiry timer has started and whose
        ``expires_utc`` is in the past.  Changes are flushed to
        the session so the caller sees updated objects immediately;
        the caller is responsible for committing the transaction.

        Args:
            vouchers: Voucher instances to inspect.
            current_time: Reference "now" (defaults to UTC now).

        Returns:
            Number of vouchers whose status was changed.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        count = 0
        for voucher in vouchers:
            if voucher.status != VoucherStatus.ACTIVE:
                continue
            if not voucher.is_activated_for_expiry:
                continue
            expires = voucher.expires_utc
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if current_time > expires:
                voucher.status = VoucherStatus.EXPIRED
                count += 1

        if count:
            self.session.flush()

        return count

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
        allowed_vlans: list[int] | None = None,
        max_devices: int = 1,
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
            allowed_vlans: Optional VLAN restriction list (1-4094)
            max_devices: Max simultaneous devices (>=1, default 1)

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
                    allowed_vlans=allowed_vlans,
                    max_devices=max_devices,
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

        # Check expiration — skip only for truly unactivated vouchers.
        if voucher.is_activated_for_expiry and voucher.expires_utc < current_time:
            voucher.status = VoucherStatus.EXPIRED
            self.voucher_repo.commit()
            raise VoucherRedemptionError(f"Voucher '{code}' expired at {voucher.expires_utc}")

        # Check for duplicate redemption (same voucher + MAC)
        existing_grants = self.grant_repo.find_pending_or_active_by_mac(mac)
        for grant in existing_grants:
            if grant.voucher_code == code:
                raise VoucherRedemptionError("Your device is already authorized with this code.")

        # Enforce multi-device limit
        active_count = self.grant_repo.count_active_by_voucher_code(code)
        if active_count >= voucher.max_devices:
            raise VoucherDeviceLimitError(
                f"Voucher '{code}' has reached its maximum of {voucher.max_devices} device(s)"
            )

        # Set activation time on first use (starts the expiry timer).
        # Guard with status check so legacy rows (redeemed_count > 0
        # but activated_utc NULL) don't get their timer restarted.
        if voucher.activated_utc is None and voucher.status == VoucherStatus.UNUSED:
            voucher.activated_utc = current_time

        # Create access grant
        grant_start = floor_to_minute(current_time)
        grant_end = grant_start + timedelta(minutes=voucher.duration_minutes)
        grant_end = ceil_to_minute(grant_end)

        grant = AccessGrant(
            voucher_code=code,
            booking_ref=voucher.booking_ref,
            mac=mac,
            device_id=mac,  # Use MAC as device_id for now
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

    async def revoke(self, code: str, current_time: Optional[datetime] = None) -> Voucher:
        """Revoke a voucher (idempotent for already-revoked).

        Args:
            code: Voucher code to revoke.
            current_time: Optional current time (defaults to now UTC).

        Returns:
            Updated voucher with REVOKED status.

        Raises:
            VoucherNotFoundError: If voucher code not found.
            VoucherExpiredError: If voucher has expired.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        voucher = self.voucher_repo.get_by_code(code)
        if not voucher:
            raise VoucherNotFoundError(code)

        if voucher.status == VoucherStatus.REVOKED:
            return voucher

        expires = voucher.expires_utc
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if voucher.is_activated_for_expiry and current_time > expires:
            voucher.status = VoucherStatus.EXPIRED
            self.voucher_repo.commit()
            raise VoucherExpiredError(code)

        voucher.status = VoucherStatus.REVOKED
        self.voucher_repo.commit()
        return voucher

    async def delete(self, code: str) -> dict[str, str | None]:
        """Hard-delete a voucher that has never been redeemed.

        Args:
            code: Voucher code to delete.

        Returns:
            Metadata dict with 'status_at_delete' and 'booking_ref'
            for audit logging by the caller.

        Raises:
            VoucherNotFoundError: If voucher code not found.
            VoucherRedeemedError: If voucher has been redeemed.
        """
        voucher = self.voucher_repo.get_by_code(code)
        if not voucher:
            raise VoucherNotFoundError(code)

        if voucher.redeemed_count > 0:
            raise VoucherRedeemedError(code)

        meta: dict[str, str | None] = {
            "status_at_delete": voucher.status.value,
            "booking_ref": voucher.booking_ref,
        }

        deleted = self.voucher_repo.delete(code)
        if not deleted:
            # Expire cached state to bypass SQLAlchemy identity map
            self.voucher_repo.session.expire_all()
            still_exists = self.voucher_repo.get_by_code(code)
            if still_exists is None:
                raise VoucherNotFoundError(code)
            else:
                raise VoucherRedeemedError(code)

        self.voucher_repo.commit()
        return meta
