# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Edge-case coverage for app-layer services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.services.audit_service import AuditService
from captive_portal.services.cache_service import get_cache
from captive_portal.services.config_migration import _secret_matches_existing
from captive_portal.services.grant_service import GrantNotFoundError, GrantService
from captive_portal.services.redirect_validator import (
    GuestExternalUrlValidator,
    RedirectValidator,
    _guest_external_url_netloc_valid,
)
from captive_portal.services.voucher_purge_service import VoucherPurgeService
from captive_portal.services.voucher_service import (
    VoucherCollisionError,
    VoucherDeviceLimitError,
    VoucherExpiredError,
    VoucherNotFoundError,
    VoucherRedeemedError,
    VoucherService,
)
from captive_portal.utils.time_utils import utc_now


class _AuditRepo:
    """Minimal audit repository double."""

    def __init__(self) -> None:
        """Initialize captured entries."""
        self.entries: list[Any] = []

    def add(self, entry: Any) -> None:
        """Capture an audit entry."""
        self.entries.append(entry)

    def commit(self) -> None:
        """Pretend to commit."""


@pytest.mark.asyncio
async def test_audit_service_logs_redemption_without_grant() -> None:
    """Voucher redemption audit metadata supports missing grant IDs."""
    repo = _AuditRepo()
    service = AuditService(cast(Session, object()), audit_repo=cast(Any, repo))

    entry = await service.log_voucher_redeemed(
        voucher_code="VOUCHER1",
        mac="AA:BB:CC:DD:EE:01",
        grant_id=cast(Any, None),
        outcome="denied",
        error="duplicate",
    )

    assert entry.actor == "guest:AA:BB:CC:DD:EE:01"
    assert entry.meta is not None
    assert entry.meta["grant_id"] is None
    assert repo.entries == [entry]


@pytest.mark.asyncio
async def test_audit_service_logs_grant_extension() -> None:
    """Grant extension audit entries include new end timestamps."""
    repo = _AuditRepo()
    service = AuditService(cast(Session, object()), audit_repo=cast(Any, repo))
    new_end = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    grant_id = uuid4()

    entry = await service.log_grant_extended(
        actor="admin",
        role="owner",
        grant_id=grant_id,
        additional_minutes=30,
        new_end_utc=new_end,
    )

    assert entry.target_id == str(grant_id)
    assert entry.meta is not None
    assert entry.meta["new_end_utc"] == new_end.isoformat()


def test_get_cache_creates_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """The global cache helper lazily creates and reuses its singleton."""
    import captive_portal.services.cache_service as cache_service

    monkeypatch.setattr(cache_service, "_cache_instance", None)

    first = get_cache()
    second = get_cache()

    assert first is second


def test_secret_matches_existing_handles_decrypt_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret comparison returns False when ciphertext cannot decrypt."""

    def fail_decrypt(_ciphertext: str, *, key_path: str) -> str:
        """Raise a synthetic decrypt failure."""
        raise ValueError(key_path)

    monkeypatch.setattr(
        "captive_portal.services.config_migration.decrypt_credential",
        fail_decrypt,
    )

    assert _secret_matches_existing("not-fernet", "plain", "missing.key") is False


def test_redirect_validator_rejects_empty_and_unknown_scheme() -> None:
    """Redirect safety rejects empty values and non-HTTP absolute schemes."""
    validator = RedirectValidator(allowed_domains=["portal.example"])

    assert validator.is_safe("") is False
    assert validator.is_safe("ftp://portal.example/path") is False
    assert validator.is_safe("https:/local-only") is False


def test_guest_external_url_rejects_bad_port_and_scheme() -> None:
    """Guest external URL validation rejects malformed authorities and schemes."""
    assert GuestExternalUrlValidator.validate("https://portal.example:bad").valid is False
    assert GuestExternalUrlValidator.validate("ftp://portal.example").valid is False


def test_guest_external_url_rejects_bad_idna_hostname() -> None:
    """Guest external URL netloc validation rejects unencodable hostnames."""
    assert _guest_external_url_netloc_valid("example.com", "\udcff") is False


def test_utc_now_returns_aware_utc_datetime() -> None:
    """utc_now returns a timezone-aware UTC timestamp."""
    now = utc_now()
    assert now.tzinfo is timezone.utc


@dataclass
class _VoucherLike:
    """Mutable voucher-like object for service branch tests."""

    code: str
    status: VoucherStatus
    is_activated_for_expiry: bool
    expires_utc: datetime
    status_changed_utc: datetime | None = None


class _FlushSession:
    """Session double that records flush calls."""

    def __init__(self) -> None:
        """Initialize flush count."""
        self.flush_count = 0

    def flush(self) -> None:
        """Record a flush call."""
        self.flush_count += 1


def test_expire_stale_vouchers_skips_unactivated_and_handles_naive() -> None:
    """Voucher expiry skips inactive timers and normalizes naive expirations."""
    session = _FlushSession()
    service = VoucherService(cast(Session, session), voucher_repo=cast(Any, object()))
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    unactivated = _VoucherLike(
        code="UNACT1",
        status=VoucherStatus.ACTIVE,
        is_activated_for_expiry=False,
        expires_utc=now - timedelta(minutes=5),
    )
    naive_expired = _VoucherLike(
        code="NAIVE1",
        status=VoucherStatus.ACTIVE,
        is_activated_for_expiry=True,
        expires_utc=(now - timedelta(minutes=5)).replace(tzinfo=None),
    )

    count = service.expire_stale_vouchers(
        cast(list[Voucher], [unactivated, naive_expired]),
        current_time=now,
    )

    assert count == 1
    assert unactivated.status == VoucherStatus.ACTIVE
    assert naive_expired.status == VoucherStatus.EXPIRED
    assert session.flush_count == 1


def test_generate_code_rejects_invalid_lengths() -> None:
    """Voucher code generation enforces supported code lengths."""
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, object()))
    with pytest.raises(ValueError, match="4-24"):
        service._generate_code(3)


@pytest.mark.asyncio
async def test_create_rejects_invalid_duration() -> None:
    """Voucher creation rejects non-positive durations."""
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, object()))
    with pytest.raises(ValueError, match="duration_minutes"):
        await service.create(duration_minutes=0)


@pytest.mark.asyncio
async def test_create_with_zero_retries_hits_collision_guard() -> None:
    """Voucher creation reports collision when no retry attempts run."""
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, object()))
    with pytest.raises(VoucherCollisionError):
        await service.create(duration_minutes=10, max_retries=0)


class _CollidingVoucherRepo:
    """Voucher repository double that always raises a collision."""

    def __init__(self) -> None:
        """Initialize rollback count."""
        self.rollbacks = 0

    def add(self, _voucher: Voucher) -> None:
        """Raise an integrity error for every add."""
        raise IntegrityError("insert", {}, Exception("duplicate"))

    def commit(self) -> None:
        """Pretend to commit."""

    def rollback(self) -> None:
        """Record rollback calls."""
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_create_exhausts_collision_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Voucher creation raises a collision error after the final retry."""
    repo = _CollidingVoucherRepo()
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, repo))

    async def no_sleep(_seconds: float) -> None:
        """Avoid test delays for retry backoff."""

    monkeypatch.setattr("captive_portal.services.voucher_service.asyncio.sleep", no_sleep)

    with pytest.raises(VoucherCollisionError, match="after 2 attempts"):
        await service.create(duration_minutes=10, max_retries=2)
    assert repo.rollbacks == 2


class _RedeemVoucherRepo:
    """Voucher repo double for redeem edge cases."""

    def __init__(self, voucher: Voucher | None) -> None:
        """Store the returned voucher."""
        self.voucher = voucher
        self.commits = 0

    def get_by_code(self, _code: str) -> Voucher | None:
        """Return the configured voucher."""
        return self.voucher

    def commit(self) -> None:
        """Record commit calls."""
        self.commits += 1


class _GrantRepo:
    """Grant repo double for redeem edge cases."""

    def __init__(self, active_count: int) -> None:
        """Store active grant count."""
        self.active_count = active_count

    def find_pending_or_active_by_mac(self, _mac: str) -> list[Any]:
        """Return no duplicate grants."""
        return []

    def count_active_by_voucher_code(self, _code: str) -> int:
        """Return the configured active count."""
        return self.active_count

    def add(self, _grant: Any) -> None:
        """Accept grant inserts."""


@pytest.mark.asyncio
async def test_redeem_enforces_max_devices() -> None:
    """Redeeming a voucher fails when the device limit is reached."""
    voucher = Voucher(code="LIMIT1", duration_minutes=30, max_devices=1)
    repo = _RedeemVoucherRepo(voucher)
    service = VoucherService(
        cast(Session, object()),
        voucher_repo=cast(Any, repo),
        grant_repo=cast(Any, _GrantRepo(active_count=1)),
    )

    with pytest.raises(VoucherDeviceLimitError, match="maximum of 1"):
        await service.redeem("LIMIT1", "AA:BB:CC:DD:EE:01")


@pytest.mark.asyncio
async def test_revoke_normalizes_naive_expiration() -> None:
    """Revoking an expired voucher normalizes naive expiry timestamps."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    voucher = Voucher(
        code="EXPIRED1",
        duration_minutes=30,
        status=VoucherStatus.ACTIVE,
        redeemed_count=1,
        activated_utc=(now - timedelta(hours=1)).replace(tzinfo=None),
    )
    repo = _RedeemVoucherRepo(voucher)
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, repo))

    with pytest.raises(VoucherExpiredError):
        await service.revoke("EXPIRED1", current_time=now)
    assert voucher.status == VoucherStatus.EXPIRED
    assert repo.commits == 1


class _DeleteRaceRepo:
    """Voucher repo double for delete race branches."""

    def __init__(self, still_exists: bool) -> None:
        """Initialize repository behavior."""
        self.voucher = Voucher(code="RACE1", duration_minutes=30)
        self.still_exists = still_exists
        self.session = self
        self.expired = False

    def get_by_code(self, _code: str) -> Voucher | None:
        """Return initial voucher or race result after expiring state."""
        if not self.expired:
            return self.voucher
        return self.voucher if self.still_exists else None

    def delete(self, _code: str) -> bool:
        """Simulate a failed conditional delete."""
        return False

    def expire_all(self) -> None:
        """Record identity-map expiry."""
        self.expired = True

    def commit(self) -> None:
        """Pretend to commit."""


@pytest.mark.asyncio
async def test_delete_raises_not_found_when_race_removes_voucher() -> None:
    """Delete maps a disappeared voucher to VoucherNotFoundError."""
    repo = _DeleteRaceRepo(still_exists=False)
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, repo))

    with pytest.raises(VoucherNotFoundError):
        await service.delete("RACE1")


@pytest.mark.asyncio
async def test_delete_raises_redeemed_when_race_leaves_voucher() -> None:
    """Delete maps a failed conditional delete with existing row to redeemed."""
    repo = _DeleteRaceRepo(still_exists=True)
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, repo))

    with pytest.raises(VoucherRedeemedError):
        await service.delete("RACE1")


class _PurgeVoucherRepo:
    """Voucher purge repository double with no purgeable rows."""

    def get_purgeable_codes(self, _cutoff: datetime) -> list[str]:
        """Return no voucher codes."""
        return []


class _UnusedGrantRepo:
    """Grant repository double that should not be called."""

    def nullify_voucher_references(self, _codes: list[str]) -> None:
        """Fail if called for an empty purge."""
        raise AssertionError("grant repo should not be used")


class _UnusedAuditService:
    """Audit service double that should not be called."""

    async def log(self, **_kwargs: Any) -> None:
        """Fail if called for an empty purge."""
        raise AssertionError("audit service should not be used")


@pytest.mark.asyncio
async def test_voucher_purge_returns_zero_without_codes() -> None:
    """Voucher purge exits early when no terminal vouchers match."""
    service = VoucherPurgeService(
        voucher_repo=cast(Any, _PurgeVoucherRepo()),
        grant_repo=cast(Any, _UnusedGrantRepo()),
        audit_service=cast(Any, _UnusedAuditService()),
    )

    assert await service.manual_purge(min_age_days=7, actor="admin") == 0


@pytest.mark.asyncio
async def test_grant_service_rejects_invalid_create_and_extend() -> None:
    """Grant service validates create windows and extension durations."""
    service = GrantService(cast(Session, object()), grant_repo=cast(Any, object()))
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="end_utc"):
        await service.create(mac="AA:BB:CC:DD:EE:01", start_utc=now, end_utc=now)
    with pytest.raises(ValueError, match="additional_minutes"):
        await service.extend(uuid4(), 0)


class _MissingGrantRepo:
    """Grant repository double that returns no grants."""

    def get_by_id(self, _grant_id: Any) -> None:
        """Return no grant for any ID."""
        return None


@pytest.mark.asyncio
async def test_grant_service_extend_missing_grant() -> None:
    """Grant extension raises when the grant ID does not exist."""
    service = GrantService(cast(Session, object()), grant_repo=cast(Any, _MissingGrantRepo()))

    with pytest.raises(GrantNotFoundError):
        await service.extend(uuid4(), 10)


class _DashboardResult:
    """Dashboard query result double."""

    def __init__(self, *, one_value: int | None = None, all_value: list[Any] | None = None) -> None:
        """Store scalar and list results."""
        self.one_value = one_value
        self.all_value = all_value or []

    def one(self) -> int:
        """Return the configured scalar value."""
        if self.one_value is None:
            raise AssertionError("one() not configured")
        return self.one_value

    def all(self) -> list[Any]:
        """Return the configured list value."""
        return self.all_value


class _DashboardSession:
    """Dashboard session double returning count and voucher rows."""

    def __init__(self) -> None:
        """Initialize query count."""
        self.calls = 0

    def exec(self, _statement: Any) -> _DashboardResult:
        """Return active count, pending count, vouchers, then integrations."""
        self.calls += 1
        if self.calls in {1, 2, 4}:
            return _DashboardResult(one_value=0)
        future_naive = datetime(2026, 1, 1, 13, 0)
        return _DashboardResult(
            all_value=[
                _VoucherLike(
                    code="DASH1",
                    status=VoucherStatus.UNUSED,
                    is_activated_for_expiry=True,
                    expires_utc=future_naive,
                ),
            ],
        )


def test_dashboard_counts_naive_future_voucher() -> None:
    """Dashboard stats normalize naive voucher expirations before counting."""
    from captive_portal.services.dashboard_service import DashboardService

    service = DashboardService(cast(Session, _DashboardSession()))
    stats = service.get_stats(current_time=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))

    assert stats.available_vouchers == 1


def test_grant_expiry_builds_adapter_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grant expiry service builds an Omada adapter for configured runtimes."""
    from captive_portal.services.grant_expiry_service import GrantExpiryService

    adapter = object()
    monkeypatch.setattr(
        "captive_portal.services.grant_expiry_service.build_omada_adapter",
        lambda _config: adapter,
    )
    service = GrantExpiryService(
        engine=cast(Any, object()),
        omada_config=cast(Any, {"controller_url": "https://omada.example"}),
    )

    assert service._build_adapter() is adapter


@dataclass
class _RevocableVoucherLike:
    """Voucher-like object with a naive expiry for revoke testing."""

    code: str
    status: VoucherStatus
    is_activated_for_expiry: bool
    expires_utc: datetime
    status_changed_utc: datetime | None = None


@pytest.mark.asyncio
async def test_revoke_replaces_naive_expiration_tzinfo() -> None:
    """Voucher revoke handles naive expiration values before comparison."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    voucher = _RevocableVoucherLike(
        code="NAIVEREVOKE",
        status=VoucherStatus.ACTIVE,
        is_activated_for_expiry=True,
        expires_utc=datetime(2026, 1, 1, 11, 0),
    )
    repo = _RedeemVoucherRepo(cast(Voucher, voucher))
    service = VoucherService(cast(Session, object()), voucher_repo=cast(Any, repo))

    with pytest.raises(VoucherExpiredError):
        await service.revoke("NAIVEREVOKE", current_time=now)
    assert voucher.status == VoucherStatus.EXPIRED
