# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Database initialization and table creation via SQLModel."""

import logging
from collections.abc import Generator
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import create_engine, Session, SQLModel

# Import all models to ensure they're registered with SQLModel metadata
from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.admin_session import AdminSession
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher

__all__ = [
    "AccessGrant",
    "AdminSession",
    "AdminUser",
    "AuditLog",
    "HAIntegrationConfig",
    "RentalControlEvent",
    "Voucher",
    "create_db_engine",
    "dispose_engine",
    "init_db",
    "get_session",
]

# Global engine instance (initialized by application)
_engine: Optional[Engine] = None


def create_db_engine(database_url: str, echo: bool = False) -> Engine:
    """Create SQLAlchemy engine for database connection.

    Args:
        database_url: Database connection URL (e.g., sqlite:///path/to/db.sqlite)
        echo: Enable SQL query logging

    Returns:
        Configured SQLAlchemy engine
    """
    global _engine
    connect_args = {}
    if database_url.startswith("sqlite"):
        # SQLite-specific: enable foreign key constraints
        connect_args = {"check_same_thread": False}

    _engine = create_engine(database_url, echo=echo, connect_args=connect_args)
    return _engine


def init_db(engine: Engine, drop_existing: bool = False) -> None:
    """Initialize database schema (create all tables).

    After table creation, applies lightweight schema migrations for
    columns added after the initial release so that existing SQLite
    databases are upgraded in-place.

    Args:
        engine: SQLAlchemy engine
        drop_existing: Drop existing tables before creation (destructive)
    """
    if drop_existing:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    _migrate_voucher_activated_utc(engine)
    _migrate_accessgrant_omada_params(engine)
    _migrate_vlan_allowed_vlans(engine)
    _migrate_voucher_max_devices(engine)


def _migrate_voucher_activated_utc(engine: Engine) -> None:
    """Add activated_utc column and backfill legacy rows.

    SQLite's CREATE TABLE IF NOT EXISTS will not add columns to
    an existing table.  This lightweight migration ensures the
    column exists for databases created before the field was
    introduced, and backfills legacy activated vouchers using
    ``created_utc`` as a best-effort approximation so upgraded
    databases preserve their original expiration behavior.

    Args:
        engine: SQLAlchemy engine to inspect and migrate.
    """
    logger = logging.getLogger("captive_portal.persistence")
    insp = inspect(engine)
    if "voucher" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("voucher")}

    with engine.begin() as conn:
        if "activated_utc" not in columns:
            conn.execute(text("ALTER TABLE voucher ADD COLUMN activated_utc DATETIME"))
            logger.info("Migrated voucher table: added activated_utc column.")

        # Backfill activated_utc for legacy redeemed vouchers.
        # Prefer created_utc because legacy expiry was calculated
        # from creation time; last_redeemed_utc is only a fallback
        # when created_utc is unexpectedly NULL.  The resulting
        # value is an approximation — it may not reflect the
        # actual first use.
        conn.execute(
            text(
                "UPDATE voucher "
                "SET activated_utc = COALESCE("
                "  created_utc, last_redeemed_utc"
                ") "
                "WHERE activated_utc IS NULL "
                "AND (redeemed_count > 0 OR status = 'active')"
            )
        )
        logger.info(
            "Migrated voucher table: backfilled activated_utc for legacy activated vouchers."
        )


def _migrate_accessgrant_omada_params(engine: Engine) -> None:
    """Add Omada connection-parameter columns to the accessgrant table.

    These columns store the gateway/AP context that was used when the
    grant was originally authorized, so the same parameters can be
    replayed during revocation (re-auth with ``time=1``).

    Args:
        engine: SQLAlchemy engine to inspect and migrate.
    """
    logger = logging.getLogger("captive_portal.persistence")
    insp = inspect(engine)
    if "accessgrant" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("accessgrant")}

    new_columns = {
        "omada_gateway_mac": "VARCHAR(17)",
        "omada_ap_mac": "VARCHAR(17)",
        "omada_vid": "VARCHAR(8)",
        "omada_ssid_name": "VARCHAR(64)",
        "omada_radio_id": "VARCHAR(2)",
    }

    with engine.begin() as conn:
        for col, col_type in new_columns.items():
            if col not in columns:
                conn.execute(text(f"ALTER TABLE accessgrant ADD COLUMN {col} {col_type}"))
                logger.info(
                    "Migrated accessgrant table: added %s column.",
                    col,
                )


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions.

    Yields:
        Database session that will be automatically closed after use.
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call create_db_engine() first.")
    with Session(_engine) as session:
        yield session


def _migrate_vlan_allowed_vlans(engine: Engine) -> None:
    """Add allowed_vlans JSON column to integration and voucher tables.

    Existing rows receive NULL (unrestricted) so deployments that
    predate VLAN isolation continue to work without configuration.

    Args:
        engine: SQLAlchemy engine to inspect and migrate.
    """
    logger = logging.getLogger("captive_portal.persistence")
    insp = inspect(engine)

    for table_name in ("ha_integration_config", "voucher"):
        if table_name not in insp.get_table_names():
            continue
        columns = {c["name"] for c in insp.get_columns(table_name)}
        if "allowed_vlans" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN allowed_vlans JSON DEFAULT NULL")
                )
            logger.info(
                "Migrated %s table: added allowed_vlans column.",
                table_name,
            )


def dispose_engine() -> None:
    """Dispose the global database engine, closing all pooled connections.

    Safe to call when no engine has been created — logs a debug message
    and returns without error.
    """
    global _engine
    if _engine is None:
        logging.getLogger("captive_portal.persistence").debug(
            "dispose_engine() called but no engine exists — no-op."
        )
        return
    _engine.dispose()
    _engine = None


def _migrate_voucher_max_devices(engine: Engine) -> None:
    """Add max_devices column to the voucher table.

    Existing rows receive the default value of 1 (single-device
    voucher) so deployments that predate multi-device support
    continue to work unchanged.

    Args:
        engine: SQLAlchemy engine to inspect and migrate.
    """
    logger = logging.getLogger("captive_portal.persistence")
    insp = inspect(engine)
    if "voucher" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("voucher")}
    if "max_devices" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE voucher ADD COLUMN max_devices INTEGER DEFAULT 1"))
        logger.info(
            "Migrated voucher table: added max_devices column.",
        )
