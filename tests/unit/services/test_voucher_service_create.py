# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test voucher service creation with duplicate prevention."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from captive_portal.models.voucher import VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.voucher_service import (
    VoucherCollisionError,
    VoucherService,
)


class TestVoucherServiceCreate:
    """Test VoucherService.create() method."""

    @pytest.mark.asyncio
    async def test_create_generates_unique_code(self, db_session: Session) -> None:
        """Create voucher generates unique A-Z0-9 code within length bounds."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=60)
        assert voucher.code.isalnum()
        assert voucher.code.isupper()
        assert 4 <= len(voucher.code) <= 24

    @pytest.mark.asyncio
    async def test_create_retries_on_collision(self, db_session: Session) -> None:
        """Create retries on PK collision with backoff."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)

        call_count = 0
        original_add = repo.add

        def flaky_add(entity):  # type: ignore[no-untyped-def]
            """Simulate a collision on first attempt."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IntegrityError("dup", {}, Exception())
            return original_add(entity)

        repo.add = flaky_add  # type: ignore[method-assign]
        voucher = await svc.create(duration_minutes=60)
        assert voucher is not None
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_create_fails_after_max_retries(self, db_session: Session) -> None:
        """Create raises exception after collision retries exhausted."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)

        def always_fail(entity):  # type: ignore[no-untyped-def]
            """Always raise IntegrityError."""
            raise IntegrityError("dup", {}, Exception())

        repo.add = always_fail  # type: ignore[method-assign]
        with pytest.raises(VoucherCollisionError):
            await svc.create(duration_minutes=60, max_retries=2)

    @pytest.mark.asyncio
    async def test_create_sets_duration_and_expires_utc(self, db_session: Session) -> None:
        """Create voucher with duration_minutes sets expires_utc correctly."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=120)
        assert voucher.duration_minutes == 120
        assert voucher.expires_utc is not None

    @pytest.mark.asyncio
    async def test_create_with_booking_ref(self, db_session: Session) -> None:
        """Create voucher with optional booking_ref (case-sensitive)."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=60, booking_ref="BookRef123")
        assert voucher.booking_ref == "BookRef123"

    @pytest.mark.asyncio
    async def test_create_with_bandwidth_limits(self, db_session: Session) -> None:
        """Create voucher with optional up/down kbps limits (nullable, >0)."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=60, up_kbps=1024, down_kbps=2048)
        assert voucher.up_kbps == 1024
        assert voucher.down_kbps == 2048

    @pytest.mark.asyncio
    async def test_create_default_status_unused(self, db_session: Session) -> None:
        """Create voucher defaults to status=UNUSED."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=60)
        assert voucher.status == VoucherStatus.UNUSED

    @pytest.mark.asyncio
    async def test_create_persists_to_repository(self, db_session: Session) -> None:
        """Create commits voucher to repository (integration with VoucherRepo)."""
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        voucher = await svc.create(duration_minutes=60)
        fetched = repo.get_by_code(voucher.code)
        assert fetched is not None
        assert fetched.code == voucher.code
