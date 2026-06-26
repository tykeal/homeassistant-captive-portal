# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Omada OpenAPI configuration schema migration."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import create_engine

from captive_portal.persistence.database import init_db


def test_init_db_adds_openapi_fields_to_existing_omada_config() -> None:
    """Existing omada_config tables gain OpenAPI fields with safe defaults."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE omada_config ("
                "id INTEGER PRIMARY KEY, "
                "controller_url VARCHAR(2048), "
                "username VARCHAR(255), "
                "encrypted_password VARCHAR(1024), "
                "site_name VARCHAR(255), "
                "controller_id VARCHAR(64), "
                "verify_ssl BOOLEAN)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO omada_config "
                "(id, controller_url, username, encrypted_password, site_name, controller_id, verify_ssl) "
                "VALUES (1, 'https://ctrl.local:8043', 'operator', 'cipher', 'Default', '', 1)"
            )
        )

    init_db(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("omada_config")}
    assert {"client_id", "encrypted_client_secret", "openapi_mode"} <= columns

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT client_id, encrypted_client_secret, openapi_mode FROM omada_config")
        ).first()
    assert row == ("", "", "auto")
