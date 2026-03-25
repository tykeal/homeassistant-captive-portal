# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dispose_engine() in database module."""

from __future__ import annotations

import os
import tempfile

from sqlmodel import Session, select

from captive_portal.persistence import database
from captive_portal.persistence.database import (
    create_db_engine,
    dispose_engine,
    init_db,
)


def test_dispose_engine_closes_connections() -> None:
    """dispose_engine() should close all pooled connections."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_db_engine(f"sqlite:///{db_path}")
        init_db(engine)

        # Verify engine works
        with Session(engine) as session:
            session.exec(select(1)).first()

        # Dispose
        dispose_engine()

        # Global engine should be None
        assert database._engine is None
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_dispose_engine_noop_without_engine() -> None:
    """dispose_engine() should be a safe no-op when no engine exists."""
    # Ensure no engine
    old_engine = database._engine
    database._engine = None

    try:
        # Should not raise
        dispose_engine()
        assert database._engine is None
    finally:
        database._engine = old_engine


def test_new_engine_after_dispose() -> None:
    """A new engine can be created and used after dispose_engine()."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_db_engine(f"sqlite:///{db_path}")
        init_db(engine)
        dispose_engine()

        # Create a new engine
        engine2 = create_db_engine(f"sqlite:///{db_path}")
        with Session(engine2) as session:
            # Should work fine
            session.exec(select(1)).first()

        dispose_engine()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
