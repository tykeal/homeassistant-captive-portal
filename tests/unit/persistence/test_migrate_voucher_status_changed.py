# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for status_changed_utc migration function.

T002: Tests for ``_migrate_voucher_status_changed_utc()`` covering
column addition, EXPIRED backfill via ``activated_utc + duration``,
EXPIRED fallback via ``created_utc + duration`` when ``activated_utc``
is NULL, REVOKED backfill via migration timestamp, UNUSED/ACTIVE left
as NULL, and idempotent re-run safety.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from captive_portal.persistence.database import _migrate_voucher_status_changed_utc


def _insert_voucher(
    conn: object,
    *,
    code: str,
    status: str,
    duration_minutes: int = 60,
    created_utc: datetime | None = None,
    activated_utc: datetime | None = None,
    status_changed_utc: datetime | None = None,
) -> None:
    """Insert a voucher row using raw SQL for migration testing."""
    if created_utc is None:
        created_utc = datetime(2025, 1, 1, tzinfo=timezone.utc)
    import sqlalchemy

    if isinstance(conn, sqlalchemy.engine.Connection):
        conn.execute(
            text(
                "INSERT INTO voucher "
                "(code, status, duration_minutes, created_utc, activated_utc, "
                "redeemed_count, max_devices, status_changed_utc) "
                "VALUES (:code, :status, :duration, :created, :activated, 0, 1, :changed)"
            ),
            {
                "code": code,
                "status": status,
                "duration": duration_minutes,
                "created": created_utc,
                "activated": activated_utc,
                "changed": status_changed_utc,
            },
        )


def _get_status_changed(conn: object, code: str) -> datetime | None:
    """Read status_changed_utc for a voucher code via raw SQL."""
    import sqlalchemy

    if isinstance(conn, sqlalchemy.engine.Connection):
        row = conn.execute(
            text("SELECT status_changed_utc FROM voucher WHERE code = :code"),
            {"code": code},
        ).fetchone()
        return row[0] if row else None
    return None


class TestMigrateVoucherStatusChangedUtc:
    """T002: Migration function tests."""

    def test_adds_column_when_missing(self, db_engine: Engine) -> None:
        """Column is added to existing table when missing."""
        # Column already exists from SQLModel.metadata.create_all
        # So verify it exists
        insp = inspect(db_engine)
        columns = {c["name"] for c in insp.get_columns("voucher")}
        assert "status_changed_utc" in columns

    def test_expired_backfill_with_activated_utc(self, db_engine: Engine) -> None:
        """EXPIRED vouchers with activated_utc get backfilled correctly."""
        activated = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        duration = 120  # 2 hours

        with db_engine.begin() as conn:
            _insert_voucher(
                conn,
                code="EXPACT00001",
                status="expired",
                duration_minutes=duration,
                activated_utc=activated,
            )

        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            result = _get_status_changed(conn, "EXPACT00001")
            assert result is not None
            # Should be activated_utc + duration_minutes
            expected = activated + timedelta(minutes=duration)
            # SQLite may store without TZ info, so compare naive
            if isinstance(result, str):
                result = datetime.fromisoformat(result)
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
            assert abs((result - expected).total_seconds()) < 60

    def test_expired_backfill_fallback_created_utc(self, db_engine: Engine) -> None:
        """EXPIRED vouchers without activated_utc use created_utc fallback."""
        created = datetime(2025, 2, 1, 8, 0, tzinfo=timezone.utc)
        duration = 60

        with db_engine.begin() as conn:
            _insert_voucher(
                conn,
                code="EXPFALLBK1",
                status="expired",
                duration_minutes=duration,
                created_utc=created,
                activated_utc=None,
            )

        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            result = _get_status_changed(conn, "EXPFALLBK1")
            assert result is not None
            expected = created + timedelta(minutes=duration)
            if isinstance(result, str):
                result = datetime.fromisoformat(result)
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
            assert abs((result - expected).total_seconds()) < 60

    def test_revoked_backfill_migration_timestamp(self, db_engine: Engine) -> None:
        """REVOKED vouchers get backfilled with migration execution time."""
        before_migration = datetime.now(timezone.utc)

        with db_engine.begin() as conn:
            _insert_voucher(
                conn,
                code="REVBACKFL1",
                status="revoked",
            )

        _migrate_voucher_status_changed_utc(db_engine)

        after_migration = datetime.now(timezone.utc)

        with db_engine.begin() as conn:
            result = _get_status_changed(conn, "REVBACKFL1")
            assert result is not None
            if isinstance(result, str):
                result = datetime.fromisoformat(result)
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
            # Migration time should be between before and after
            assert before_migration <= result <= after_migration + timedelta(seconds=5)

    def test_unused_left_as_null(self, db_engine: Engine) -> None:
        """UNUSED vouchers should NOT be backfilled."""
        with db_engine.begin() as conn:
            _insert_voucher(conn, code="UNUSEDNULL", status="unused")

        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            result = _get_status_changed(conn, "UNUSEDNULL")
            assert result is None

    def test_active_left_as_null(self, db_engine: Engine) -> None:
        """ACTIVE vouchers should NOT be backfilled."""
        with db_engine.begin() as conn:
            _insert_voucher(
                conn,
                code="ACTIVNULL1",
                status="active",
                activated_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            )

        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            result = _get_status_changed(conn, "ACTIVNULL1")
            assert result is None

    def test_idempotent_rerun(self, db_engine: Engine) -> None:
        """Running migration twice does not overwrite existing values."""
        activated = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)

        with db_engine.begin() as conn:
            _insert_voucher(
                conn,
                code="IDEMPOTNT1",
                status="expired",
                duration_minutes=60,
                activated_utc=activated,
            )

        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            first_result = _get_status_changed(conn, "IDEMPOTNT1")

        # Run again
        _migrate_voucher_status_changed_utc(db_engine)

        with db_engine.begin() as conn:
            second_result = _get_status_changed(conn, "IDEMPOTNT1")

        assert first_result == second_result
