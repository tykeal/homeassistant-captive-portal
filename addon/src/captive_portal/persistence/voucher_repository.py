# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Voucher repository implementation."""

from datetime import datetime
from typing import Any, Optional, cast

from sqlmodel import col, select

from captive_portal.models.voucher import Voucher
from captive_portal.persistence.repository_base import BaseRepository


class VoucherRepository(BaseRepository[Voucher]):
    """Repository for Voucher entities."""

    def get_model_class(self) -> type[Voucher]:
        """Return Voucher model class."""
        return Voucher

    def get_by_code(self, code: str) -> Optional[Voucher]:
        """Retrieve voucher by code (PK).

        Args:
            code: Voucher code.

        Returns:
            Voucher instance or None.
        """
        return cast(Optional[Voucher], self.session.get(Voucher, code))

    def find_by_booking_ref(self, booking_ref: str) -> list[Voucher]:
        """Find vouchers by booking reference (case-sensitive).

        Args:
            booking_ref: Booking reference.

        Returns:
            List of matching vouchers.
        """
        statement: Any = select(Voucher).where(Voucher.booking_ref == booking_ref)
        results: list[Voucher] = list(self.session.exec(statement).all())
        return results

    def delete(self, code: str) -> bool:
        """Delete a voucher by code if it has never been redeemed.

        Uses a predicate-based delete to guard against race conditions:
        only deletes if redeemed_count == 0.

        Args:
            code: Voucher code (PK).

        Returns:
            True if the row was deleted, False otherwise.
        """
        from sqlalchemy import delete as sa_delete

        stmt = sa_delete(Voucher).where(
            Voucher.code == code,  # type: ignore[arg-type]
            Voucher.redeemed_count == 0,  # type: ignore[arg-type]
        )
        result: Any = self.session.execute(stmt)
        if result.rowcount == 1:
            self.session.flush()
            return True
        return False

    def count_purgeable(self, cutoff: datetime) -> int:
        """Count vouchers eligible for purge.

        Counts vouchers in EXPIRED or REVOKED status whose age
        reference is before the given cutoff. The age reference is
        ``COALESCE(status_changed_utc, created_utc)`` so vouchers
        lacking ``status_changed_utc`` fall back to ``created_utc``.

        Args:
            cutoff: Cutoff datetime; vouchers whose age reference is
                before this are eligible.

        Returns:
            Count of purgeable vouchers.
        """
        from sqlalchemy import func
        from sqlalchemy.sql.functions import coalesce

        from captive_portal.models.voucher import VoucherStatus

        cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
        age_ref = coalesce(Voucher.status_changed_utc, Voucher.created_utc)

        statement: Any = (
            select(func.count())
            .select_from(Voucher)
            .where(col(Voucher.status).in_([VoucherStatus.EXPIRED, VoucherStatus.REVOKED]))
            .where(age_ref < cutoff_naive)
        )
        result: int = self.session.exec(statement).one()
        return result

    def get_purgeable_codes(self, cutoff: datetime) -> list[str]:
        """Return codes of vouchers eligible for purge.

        Args:
            cutoff: Cutoff datetime.

        Returns:
            List of voucher codes eligible for purge.
        """
        from sqlalchemy.sql.functions import coalesce

        from captive_portal.models.voucher import VoucherStatus

        cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
        age_ref = coalesce(Voucher.status_changed_utc, Voucher.created_utc)

        statement: Any = (
            select(Voucher.code)
            .where(col(Voucher.status).in_([VoucherStatus.EXPIRED, VoucherStatus.REVOKED]))
            .where(age_ref < cutoff_naive)
        )
        results: list[str] = list(self.session.exec(statement).all())
        return results

    def purge(self, cutoff: datetime) -> int:
        """Delete vouchers eligible for purge.

        Args:
            cutoff: Cutoff datetime.

        Returns:
            Number of deleted vouchers.
        """
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.sql.functions import coalesce

        from captive_portal.models.voucher import VoucherStatus

        cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
        age_ref = coalesce(Voucher.status_changed_utc, Voucher.created_utc)

        stmt = (
            sa_delete(Voucher)
            .where(col(Voucher.status).in_([VoucherStatus.EXPIRED, VoucherStatus.REVOKED]))
            .where(age_ref < cutoff_naive)
        )
        result: Any = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount)
