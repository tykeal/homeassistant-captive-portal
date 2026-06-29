# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for database initialization and SQLite migrations."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from captive_portal.models.portal_config import PortalConfig
from captive_portal.persistence import database


def _engine() -> Engine:
    """Create an isolated in-memory SQLite engine."""
    return create_engine("sqlite://", connect_args={"check_same_thread": False})


def _columns(engine: Engine, table_name: str) -> set[str]:
    """Return column names for a SQLite table."""
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _scalar(engine: Engine, query: str) -> Any:
    """Return the first scalar value for a SQL statement."""
    with engine.connect() as conn:
        return conn.execute(text(query)).scalar_one()


def test_init_db_drop_existing_recreates_registered_tables() -> None:
    """init_db drops existing metadata tables before recreating the schema."""
    engine = _engine()
    database.init_db(engine)

    with Session(engine) as session:
        session.add(PortalConfig())
        session.commit()

    database.init_db(engine, drop_existing=True)

    assert "portal_config" in inspect(engine).get_table_names()
    assert _scalar(engine, "SELECT COUNT(*) FROM portal_config") == 0


def test_get_session_requires_initialized_engine() -> None:
    """get_session raises a clear error before create_db_engine is called."""
    database.dispose_engine()

    with pytest.raises(RuntimeError, match="Database engine not initialized"):
        next(database.get_session())


def test_create_db_engine_sets_global_engine_for_sessions() -> None:
    """create_db_engine stores the engine used by get_session."""
    engine = database.create_db_engine("sqlite://")

    try:
        session_iter: Generator[Session, None, None] = database.get_session()
        session = next(session_iter)
        try:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
        finally:
            session_iter.close()
    finally:
        database.dispose_engine()
        engine.dispose()


def test_migrations_skip_missing_tables() -> None:
    """Migration helpers are no-ops when their target tables do not exist."""
    engine = _engine()

    database._migrate_voucher_activated_utc(engine)
    database._migrate_accessgrant_omada_params(engine)
    database._migrate_vlan_allowed_vlans(engine)
    database._migrate_voucher_max_devices(engine)
    database._migrate_voucher_status_changed_utc(engine)
    database._migrate_portal_config_session_fields(engine)
    database._migrate_omada_openapi_fields(engine)

    assert inspect(engine).get_table_names() == []


def test_voucher_migrations_add_columns_and_backfill_values() -> None:
    """Voucher migrations preserve legacy rows while adding new fields."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE voucher ("
                "code VARCHAR PRIMARY KEY, "
                "created_utc DATETIME, "
                "duration_minutes INTEGER, "
                "status VARCHAR, "
                "redeemed_count INTEGER, "
                "last_redeemed_utc DATETIME"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO voucher "
                "(code, created_utc, duration_minutes, status, redeemed_count, last_redeemed_utc) "
                "VALUES "
                "('LEGACY001', '2026-01-01 10:00:00', 60, 'active', 1, "
                " '2026-01-01 10:05:00'), "
                "('LEGACY002', '2026-01-02 10:00:00', 30, 'expired', 0, NULL), "
                "('LEGACY003', '2026-01-03 10:00:00', 30, 'revoked', 0, NULL)"
            )
        )

    database._migrate_voucher_activated_utc(engine)
    database._migrate_voucher_max_devices(engine)
    database._migrate_voucher_status_changed_utc(engine)

    assert {"activated_utc", "max_devices", "status_changed_utc"} <= _columns(engine, "voucher")
    assert _scalar(engine, "SELECT activated_utc FROM voucher WHERE code = 'LEGACY001'") == (
        "2026-01-01 10:00:00"
    )
    assert _scalar(engine, "SELECT max_devices FROM voucher WHERE code = 'LEGACY001'") == 1
    assert _scalar(engine, "SELECT status_changed_utc FROM voucher WHERE code = 'LEGACY002'") == (
        "2026-01-02 10:30:00"
    )
    assert (
        _scalar(
            engine, "SELECT status_changed_utc IS NOT NULL FROM voucher WHERE code = 'LEGACY003'"
        )
        == 1
    )

    with engine.begin() as conn:
        conn.execute(text("UPDATE voucher SET max_devices = NULL WHERE code = 'LEGACY001'"))

    database._migrate_voucher_max_devices(engine)

    assert _scalar(engine, "SELECT max_devices FROM voucher WHERE code = 'LEGACY001'") == 1


def test_accessgrant_migration_adds_omada_replay_columns() -> None:
    """Access grant migration adds Omada connection replay parameters."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accessgrant (id VARCHAR PRIMARY KEY)"))

    database._migrate_accessgrant_omada_params(engine)

    assert {
        "omada_gateway_mac",
        "omada_ap_mac",
        "omada_vid",
        "omada_ssid_name",
        "omada_radio_id",
    } <= _columns(engine, "accessgrant")


def test_vlan_migration_adds_allowed_vlans_to_config_and_voucher() -> None:
    """VLAN migration adds nullable allowed_vlans columns to both tables."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ha_integration_config (id VARCHAR PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE voucher (code VARCHAR PRIMARY KEY)"))

    database._migrate_vlan_allowed_vlans(engine)

    assert "allowed_vlans" in _columns(engine, "ha_integration_config")
    assert "allowed_vlans" in _columns(engine, "voucher")


def test_portal_config_migration_adds_session_and_guest_url_fields() -> None:
    """Portal config migration adds session timeout and guest URL fields."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE portal_config (id INTEGER PRIMARY KEY)"))

    database._migrate_portal_config_session_fields(engine)

    assert {"session_idle_minutes", "session_max_hours", "guest_external_url"} <= _columns(
        engine,
        "portal_config",
    )


def test_omada_migration_adds_openapi_fields_and_defaults() -> None:
    """Omada migration adds OpenAPI fields and normalizes legacy rows."""
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE omada_config (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO omada_config (id) VALUES (1)"))

    database._migrate_omada_openapi_fields(engine)

    assert {"client_id", "encrypted_client_secret", "openapi_mode"} <= _columns(
        engine,
        "omada_config",
    )
    assert _scalar(engine, "SELECT client_id FROM omada_config WHERE id = 1") == ""
    assert _scalar(engine, "SELECT encrypted_client_secret FROM omada_config WHERE id = 1") == ""
    assert _scalar(engine, "SELECT openapi_mode FROM omada_config WHERE id = 1") == "auto"
