# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for integration tests."""

from typing import Any

import pytest
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser


@pytest.fixture
def empty_admin_table(db_session: Session) -> Any:
    """Ensure admin table is empty for the duration of the test."""
    admins = list(db_session.exec(select(AdminUser)).all())
    for admin in admins:
        db_session.delete(admin)
    db_session.commit()
    yield
    admins = list(db_session.exec(select(AdminUser)).all())
    for admin in admins:
        db_session.delete(admin)
    db_session.commit()
