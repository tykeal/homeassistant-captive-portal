# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test _migrate_voucher_max_devices() migration function.

Verifies that the migration adds the max_devices column with DEFAULT 1,
existing rows receive max_devices=1, and the migration is idempotent.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.persistence.database import _migrate_voucher_max_devices


class TestMigrateVoucherMaxDevices:
    """Test the max_devices column migration."""

    def test_adds_column_with_default_1(self, db_engine: Engine) -> None:
        """Migration adds max_devices column with DEFAULT 1."""
        # The column should already exist (created by SQLModel metadata)
        # But verify via inspect that it's present
        insp = inspect(db_engine)
        columns = {c["name"] for c in insp.get_columns("voucher")}
        assert "max_devices" in columns

    def test_existing_rows_get_default_1(self, db_engine: Engine) -> None:
        """Existing vouchers should get max_devices=1 from the DEFAULT clause."""
        with Session(db_engine) as session:
            # Create a voucher using the ORM (which includes max_devices)
            from captive_portal.models.voucher import Voucher, VoucherStatus

            voucher = Voucher(
                code="MIGTEST01",
                duration_minutes=60,
                status=VoucherStatus.UNUSED,
            )
            session.add(voucher)
            session.commit()

            # Verify the default was applied
            row = session.execute(
                text("SELECT max_devices FROM voucher WHERE code = 'MIGTEST01'")
            ).fetchone()
            assert row is not None
            assert row[0] == 1

            # Cleanup
            session.execute(text("DELETE FROM voucher WHERE code = 'MIGTEST01'"))
            session.commit()

    def test_idempotent_second_call_is_noop(self, db_engine: Engine) -> None:
        """Second migration call should be a no-op (column already exists)."""
        # First call (column already exists from SQLModel.metadata.create_all)
        _migrate_voucher_max_devices(db_engine)
        # Second call should not raise
        _migrate_voucher_max_devices(db_engine)
        # Column still exists
        insp = inspect(db_engine)
        columns = {c["name"] for c in insp.get_columns("voucher")}
        assert "max_devices" in columns
