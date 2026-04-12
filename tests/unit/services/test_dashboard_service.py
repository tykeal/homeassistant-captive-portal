# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DashboardService statistics and activity log."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.security.password_hashing import hash_password
from captive_portal.services.dashboard_service import (
    ActivityLogEntry,
    DashboardService,
    DashboardStats,
)

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ── helpers ──────────────────────────────────────────────────────────


def _make_grant(
    db_session: Session,
    *,
    device_id: str = "dev-1",
    mac: str = "AA:BB:CC:DD:EE:01",
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
    status: GrantStatus = GrantStatus.ACTIVE,
) -> AccessGrant:
    """Create a test AccessGrant instance."""
    start = start_utc or (NOW - timedelta(hours=1))
    end = end_utc or (NOW + timedelta(hours=1))
    grant = AccessGrant(
        device_id=device_id,
        mac=mac,
        start_utc=start,
        end_utc=end,
        status=status,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


def _make_voucher(
    db_session: Session,
    *,
    code: str,
    duration_minutes: int = 1440,
    status: VoucherStatus = VoucherStatus.UNUSED,
    created_utc: datetime | None = None,
    activated_utc: datetime | None = None,
) -> Voucher:
    """Create a test Voucher instance."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=0,
    )
    if created_utc is not None:
        voucher.created_utc = created_utc
    if activated_utc is not None:
        voucher.activated_utc = activated_utc
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


def _make_integration(db_session: Session, *, integration_id: str) -> HAIntegrationConfig:
    """Create a test HAIntegrationConfig instance."""
    config = HAIntegrationConfig(integration_id=integration_id)
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


def _make_admin(db_session: Session, *, username: str = "testadmin") -> AdminUser:
    """Create a test AdminUser instance."""
    admin = AdminUser(
        username=username,
        password_hash=hash_password("SecureP@ss123"),
        email=f"{username}@example.com",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _make_audit_log(
    db_session: Session,
    *,
    actor: str = "system",
    action: str = "test.action",
    target_type: str = "grant",
    target_id: str = "id-1",
    timestamp_utc: datetime | None = None,
) -> AuditLog:
    """Create a test AuditLog instance."""
    log = AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        outcome="success",
    )
    if timestamp_utc is not None:
        log.timestamp_utc = timestamp_utc
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


# ── get_stats tests ─────────────────────────────────────────────────


class TestGetStatsZeroData:
    """get_stats() on an empty database."""

    def test_returns_all_zeros(self, db_session: Session) -> None:
        """All stat counters are zero when no data exists."""
        svc = DashboardService(db_session)
        stats = svc.get_stats(current_time=NOW)

        assert isinstance(stats, DashboardStats)
        assert stats.active_grants == 0
        assert stats.pending_grants == 0
        assert stats.available_vouchers == 0
        assert stats.integrations == 0


class TestGetStatsNormalData:
    """get_stats() with a mix of grants, vouchers, and integrations."""

    def test_counts_all_categories(self, db_session: Session) -> None:
        """Verify correct counts across active grants, pending grants,
        available vouchers, and integrations."""
        # 1 active grant (started, not ended)
        _make_grant(db_session, device_id="d1", mac="AA:BB:CC:DD:EE:01")
        # 1 pending grant (starts in the future)
        _make_grant(
            db_session,
            device_id="d2",
            mac="AA:BB:CC:DD:EE:02",
            start_utc=NOW + timedelta(hours=1),
            end_utc=NOW + timedelta(hours=3),
        )
        # 1 unused voucher (not expired)
        _make_voucher(
            db_session,
            code="AAAA1111",
            created_utc=NOW - timedelta(hours=1),
        )
        # 2 integrations
        _make_integration(db_session, integration_id="int-1")
        _make_integration(db_session, integration_id="int-2")

        svc = DashboardService(db_session)
        stats = svc.get_stats(current_time=NOW)

        assert stats.active_grants == 1
        assert stats.pending_grants == 1
        assert stats.available_vouchers == 1
        assert stats.integrations == 2


class TestGetStatsActiveGrants:
    """Active grants: status != REVOKED, start_utc <= now, end_utc > now."""

    def test_grant_spanning_now_is_active(self, db_session: Session) -> None:
        """Verify grant spanning current time is counted as active."""
        _make_grant(
            db_session,
            start_utc=NOW - timedelta(hours=1),
            end_utc=NOW + timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 1

    def test_grant_starting_exactly_now_is_active(self, db_session: Session) -> None:
        """Verify grant starting exactly at current time is counted as active."""
        _make_grant(db_session, start_utc=NOW, end_utc=NOW + timedelta(hours=1))
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 1

    def test_pending_status_still_counted_as_active_by_time(self, db_session: Session) -> None:
        """The query uses time bounds, not the status field, so a PENDING
        grant whose window includes 'now' counts as active."""
        _make_grant(
            db_session,
            status=GrantStatus.PENDING,
            start_utc=NOW - timedelta(minutes=30),
            end_utc=NOW + timedelta(minutes=30),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 1


class TestGetStatsPendingGrants:
    """Pending grants: status != REVOKED, start_utc > now."""

    def test_future_grant_is_pending(self, db_session: Session) -> None:
        """Verify future grant is counted as pending."""
        _make_grant(
            db_session,
            start_utc=NOW + timedelta(hours=1),
            end_utc=NOW + timedelta(hours=3),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.pending_grants == 1
        assert stats.active_grants == 0

    def test_grant_starting_exactly_now_not_pending(self, db_session: Session) -> None:
        """start_utc == now means the grant has started, so it is active, not pending."""
        _make_grant(db_session, start_utc=NOW, end_utc=NOW + timedelta(hours=1))
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.pending_grants == 0


class TestGetStatsAvailableVouchers:
    """Available vouchers: status == UNUSED and expires_utc > now."""

    def test_unused_unexpired_voucher_counted(self, db_session: Session) -> None:
        """Verify unused unexpired voucher is counted as available."""
        _make_voucher(
            db_session,
            code="VVVV0001",
            duration_minutes=1440,
            created_utc=NOW - timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.available_vouchers == 1

    def test_expired_unused_voucher_not_counted(self, db_session: Session) -> None:
        """Verify activated-then-expired unused voucher is not counted."""
        past = NOW - timedelta(hours=2)
        _make_voucher(
            db_session,
            code="VVVV0002",
            duration_minutes=60,
            created_utc=past,
            activated_utc=past,
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.available_vouchers == 0

    def test_unactivated_old_voucher_still_counted(self, db_session: Session) -> None:
        """Unactivated voucher is available regardless of creation age."""
        _make_voucher(
            db_session,
            code="VVVV0005",
            duration_minutes=60,
            created_utc=NOW - timedelta(hours=2),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.available_vouchers == 1

    def test_active_voucher_not_counted(self, db_session: Session) -> None:
        """Verify active voucher is not counted as available."""
        _make_voucher(
            db_session,
            code="VVVV0003",
            status=VoucherStatus.ACTIVE,
            created_utc=NOW - timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.available_vouchers == 0

    def test_revoked_voucher_not_counted(self, db_session: Session) -> None:
        """Verify revoked voucher is not counted as available."""
        _make_voucher(
            db_session,
            code="VVVV0004",
            status=VoucherStatus.REVOKED,
            created_utc=NOW - timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.available_vouchers == 0


class TestGetStatsIntegrations:
    """Integrations: count of all HAIntegrationConfig rows."""

    def test_counts_all_integrations(self, db_session: Session) -> None:
        """Verify all integration configs are counted."""
        _make_integration(db_session, integration_id="ha-1")
        _make_integration(db_session, integration_id="ha-2")
        _make_integration(db_session, integration_id="ha-3")
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.integrations == 3


class TestGetStatsRevokedExcluded:
    """Revoked grants excluded from both active and pending counts."""

    def test_revoked_active_window_not_counted(self, db_session: Session) -> None:
        """Verify revoked grant in active window is not counted as active."""
        _make_grant(
            db_session,
            status=GrantStatus.REVOKED,
            start_utc=NOW - timedelta(hours=1),
            end_utc=NOW + timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 0

    def test_revoked_future_grant_not_counted(self, db_session: Session) -> None:
        """Verify revoked future grant is not counted as pending."""
        _make_grant(
            db_session,
            status=GrantStatus.REVOKED,
            start_utc=NOW + timedelta(hours=1),
            end_utc=NOW + timedelta(hours=3),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.pending_grants == 0


class TestGetStatsExpiredExcluded:
    """Expired grants (end_utc < now) excluded from active count."""

    def test_expired_grant_not_active(self, db_session: Session) -> None:
        """Verify expired grant is not counted as active."""
        _make_grant(
            db_session,
            start_utc=NOW - timedelta(hours=3),
            end_utc=NOW - timedelta(hours=1),
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 0

    def test_grant_ending_exactly_now_not_active(self, db_session: Session) -> None:
        """end_utc == now means the grant has expired (end_utc > now is required)."""
        _make_grant(
            db_session,
            start_utc=NOW - timedelta(hours=1),
            end_utc=NOW,
        )
        stats = DashboardService(db_session).get_stats(current_time=NOW)
        assert stats.active_grants == 0


# ── get_recent_activity tests ───────────────────────────────────────


class TestGetRecentActivityEmpty:
    """get_recent_activity() with no audit logs."""

    def test_returns_empty_list(self, db_session: Session) -> None:
        """Verify empty list returned when no audit logs exist."""
        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()
        assert entries == []


class TestGetRecentActivityOrdering:
    """get_recent_activity() returns entries ordered by timestamp DESC."""

    def test_ordered_by_timestamp_desc(self, db_session: Session) -> None:
        """Verify entries are ordered by timestamp descending."""
        t1 = NOW - timedelta(hours=3)
        t2 = NOW - timedelta(hours=2)
        t3 = NOW - timedelta(hours=1)

        _make_audit_log(db_session, action="first", timestamp_utc=t1)
        _make_audit_log(db_session, action="second", timestamp_utc=t2)
        _make_audit_log(db_session, action="third", timestamp_utc=t3)

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()

        assert len(entries) == 3
        assert entries[0].action == "third"
        assert entries[1].action == "second"
        assert entries[2].action == "first"


class TestGetRecentActivityLimit:
    """get_recent_activity() respects the limit parameter."""

    def test_default_limit_is_20(self, db_session: Session) -> None:
        """Verify default limit of 20 entries is applied."""
        for i in range(25):
            _make_audit_log(
                db_session,
                action=f"action-{i:02d}",
                target_id=f"id-{i:02d}",
                timestamp_utc=NOW - timedelta(minutes=25 - i),
            )

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()
        assert len(entries) == 20

    def test_custom_limit(self, db_session: Session) -> None:
        """Verify custom limit parameter restricts result count."""
        for i in range(10):
            _make_audit_log(
                db_session,
                action=f"action-{i}",
                target_id=f"id-{i}",
                timestamp_utc=NOW - timedelta(minutes=10 - i),
            )

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity(limit=5)
        assert len(entries) == 5


class TestGetRecentActivityAdminResolution:
    """get_recent_activity() resolves admin UUIDs to usernames."""

    def test_resolves_admin_uuid_to_username(self, db_session: Session) -> None:
        """Verify admin UUID is resolved to username."""
        admin = _make_admin(db_session, username="alice")
        _make_audit_log(db_session, actor=str(admin.id), action="grant.create")

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()

        assert len(entries) == 1
        assert entries[0].admin_username == "alice"

    def test_falls_back_to_raw_actor_for_non_uuid(self, db_session: Session) -> None:
        """Verify non-UUID actor falls back to raw actor string."""
        _make_audit_log(db_session, actor="system", action="cleanup.run")

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()

        assert len(entries) == 1
        assert entries[0].admin_username == "system"

    def test_falls_back_to_raw_uuid_when_admin_not_found(self, db_session: Session) -> None:
        """A valid UUID that doesn't match any AdminUser falls back to the raw string."""
        fake_uuid = "00000000-0000-0000-0000-000000000099"
        _make_audit_log(db_session, actor=fake_uuid, action="grant.revoke")

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()

        assert len(entries) == 1
        assert entries[0].admin_username == fake_uuid


class TestGetRecentActivityEntryFields:
    """Verify all ActivityLogEntry fields are correctly populated."""

    def test_entry_fields(self, db_session: Session) -> None:
        """Verify all ActivityLogEntry fields are correctly populated."""
        ts = NOW - timedelta(minutes=5)
        _make_audit_log(
            db_session,
            actor="system",
            action="voucher.create",
            target_type="voucher",
            target_id="ABCD1234",
            timestamp_utc=ts,
        )

        svc = DashboardService(db_session)
        entries = svc.get_recent_activity()

        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, ActivityLogEntry)
        assert entry.action == "voucher.create"
        assert entry.target_type == "voucher"
        assert entry.target_id == "ABCD1234"
        assert entry.admin_username == "system"
        assert isinstance(entry.timestamp, datetime)
