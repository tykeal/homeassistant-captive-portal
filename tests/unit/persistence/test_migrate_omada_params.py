# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for _migrate_accessgrant_omada_params migration."""

from __future__ import annotations

import os
import tempfile

from sqlalchemy import inspect, text

from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)


def test_migration_adds_omada_columns_to_legacy_table() -> None:
    """init_db() should add Omada param columns to a legacy accessgrant table."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_db_engine(f"sqlite:///{db_path}")

        # Create all tables first (full schema)
        init_db(engine)

        # Drop the Omada columns to simulate a legacy database
        omada_cols = [
            "omada_gateway_mac",
            "omada_ap_mac",
            "omada_vid",
            "omada_ssid_name",
            "omada_radio_id",
        ]
        # SQLite doesn't support DROP COLUMN before 3.35.0 —
        # recreate the table without the columns instead.
        insp = inspect(engine)
        all_cols = insp.get_columns("accessgrant")
        keep_cols = [c["name"] for c in all_cols if c["name"] not in omada_cols]
        cols_csv = ", ".join(keep_cols)

        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE TABLE accessgrant_backup AS SELECT {cols_csv} FROM accessgrant")
            )
            conn.execute(text("DROP TABLE accessgrant"))
            conn.execute(text("ALTER TABLE accessgrant_backup RENAME TO accessgrant"))

        # Verify the columns are missing
        insp = inspect(engine)
        existing = {c["name"] for c in insp.get_columns("accessgrant")}
        for col in omada_cols:
            assert col not in existing, f"{col} should not exist yet"

        # Re-run init_db — migration should add the missing columns
        init_db(engine)

        insp = inspect(engine)
        migrated = {c["name"] for c in insp.get_columns("accessgrant")}
        for col in omada_cols:
            assert col in migrated, f"{col} should be added by migration"

        dispose_engine()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_migration_is_idempotent() -> None:
    """Running init_db() twice should not fail on already-migrated columns."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_db_engine(f"sqlite:///{db_path}")
        init_db(engine)
        # Second call should be a no-op (no error)
        init_db(engine)

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("accessgrant")}
        assert "omada_gateway_mac" in cols

        dispose_engine()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
