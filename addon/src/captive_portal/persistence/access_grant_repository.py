# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Access grant repository implementation."""

from typing import Any, Optional, cast
from uuid import UUID

from sqlmodel import col, select

from captive_portal.models.access_grant import AccessGrant
from captive_portal.persistence.repository_base import BaseRepository


class AccessGrantRepository(BaseRepository[AccessGrant]):
    """Repository for AccessGrant entities."""

    def get_model_class(self) -> type[AccessGrant]:
        """Return AccessGrant model class."""
        return AccessGrant

    def get_by_id(self, grant_id: UUID) -> Optional[AccessGrant]:
        """Retrieve grant by ID.

        Args:
            grant_id: Grant UUID.

        Returns:
            AccessGrant instance or None.
        """
        return cast(Optional[AccessGrant], self.session.get(AccessGrant, grant_id))

    def find_active_by_mac(self, mac: str) -> list[AccessGrant]:
        """Find active grants for MAC address.

        Args:
            mac: Device MAC address.

        Returns:
            List of active grants.
        """
        from captive_portal.models.access_grant import GrantStatus

        statement: Any = (
            select(AccessGrant)
            .where(AccessGrant.mac == mac)
            .where(AccessGrant.status == GrantStatus.ACTIVE)
        )
        results: list[AccessGrant] = list(self.session.exec(statement).all())
        return results

    def find_pending_or_active_by_mac(self, mac: str) -> list[AccessGrant]:
        """Find pending or active grants for MAC address.

        Args:
            mac: Device MAC address.

        Returns:
            List of pending or active grants.
        """
        from captive_portal.models.access_grant import GrantStatus

        statement: Any = (
            select(AccessGrant)
            .where(AccessGrant.mac == mac)
            .where(col(AccessGrant.status).in_([GrantStatus.PENDING, GrantStatus.ACTIVE]))
        )
        results: list[AccessGrant] = list(self.session.exec(statement).all())
        return results

    def count_active_by_voucher_code(self, code: str) -> int:
        """Count active or pending grants for a voucher code.

        Args:
            code: Voucher code to count grants for.

        Returns:
            Number of grants with status pending or active.
        """
        from sqlalchemy import func

        from captive_portal.models.access_grant import GrantStatus

        statement: Any = (
            select(func.count())
            .select_from(AccessGrant)
            .where(AccessGrant.voucher_code == code)
            .where(col(AccessGrant.status).in_([GrantStatus.PENDING, GrantStatus.ACTIVE]))
        )
        result: int = self.session.exec(statement).one()
        return result

    def count_active_by_voucher_codes(self, codes: list[str]) -> dict[str, int]:
        """Batch-count active or pending grants per voucher code.

        Args:
            codes: List of voucher codes to count.

        Returns:
            Mapping of code to count (codes with zero are omitted).
        """
        if not codes:
            return {}

        from sqlalchemy import func

        from captive_portal.models.access_grant import GrantStatus

        statement: Any = (
            select(AccessGrant.voucher_code, func.count())
            .where(col(AccessGrant.voucher_code).in_(codes))
            .where(col(AccessGrant.status).in_([GrantStatus.PENDING, GrantStatus.ACTIVE]))
            .group_by(AccessGrant.voucher_code)
        )
        rows = self.session.exec(statement).all()
        return {code: count for code, count in rows}

    def nullify_voucher_references(self, voucher_codes: list[str]) -> int:
        """Set voucher_code to NULL for grants referencing voucher codes.

        Args:
            voucher_codes: List of voucher codes being purged.

        Returns:
            Number of grant records updated.
        """
        if not voucher_codes:
            return 0

        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(AccessGrant)
            .where(col(AccessGrant.voucher_code).in_(voucher_codes))
            .values(voucher_code=None)
        )
        result: Any = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount)
