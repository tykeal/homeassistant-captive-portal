# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Database initialization and table creation via SQLModel."""

from sqlalchemy.engine import Engine
from sqlmodel import create_engine, SQLModel

# Import all models to ensure they're registered with SQLModel metadata
from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher

__all__ = [
    "AccessGrant",
    "AdminUser",
    "AuditLog",
    "HAIntegrationConfig",
    "RentalControlEvent",
    "Voucher",
    "create_db_engine",
    "init_db",
]


def create_db_engine(database_url: str, echo: bool = False) -> Engine:
    """Create SQLAlchemy engine for database connection.

    Args:
        database_url: Database connection URL (e.g., sqlite:///path/to/db.sqlite)
        echo: Enable SQL query logging

    Returns:
        Configured SQLAlchemy engine
    """
    connect_args = {}
    if database_url.startswith("sqlite"):
        # SQLite-specific: enable foreign key constraints
        connect_args = {"check_same_thread": False}

    return create_engine(database_url, echo=echo, connect_args=connect_args)


def init_db(engine: Engine, drop_existing: bool = False) -> None:
    """Initialize database schema (create all tables).

    Args:
        engine: SQLAlchemy engine
        drop_existing: Drop existing tables before creation (destructive)
    """
    if drop_existing:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
