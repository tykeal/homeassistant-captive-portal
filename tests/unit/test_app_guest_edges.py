# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Targeted edge-case coverage for app and guest app modules."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message

from captive_portal.config.settings import AppSettings
from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
from captive_portal.guest_debug import DebugLoggingMiddleware
from captive_portal.guest_errors import register_guest_exception_handlers
from captive_portal.guest_routes import mount_guest_static
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.services.config_migration import MigrationResult


@pytest.mark.asyncio
async def test_app_config_migration_logs_all_successes(
    db_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Admin app migration logs every migrated setting category."""
    app_module = importlib.import_module("captive_portal.app")

    migration = AsyncMock(
        return_value=MigrationResult(
            omada_migrated=True,
            session_fields_migrated=2,
            guest_url_migrated=True,
        ),
    )
    monkeypatch.setattr("captive_portal.services.config_migration.migrate_yaml_to_db", migration)

    with caplog.at_level(logging.INFO, logger="captive_portal"):
        await app_module._run_config_migration(AppSettings(db_path=":memory:"), db_engine)

    assert "Omada settings migrated" in caplog.text
    assert "2 session fields migrated" in caplog.text
    assert "guest_external_url migrated" in caplog.text
    migration.assert_awaited_once()


@pytest.mark.asyncio
async def test_guest_config_migration_logs_successes_and_failures(
    db_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guest app migration logs successes and treats failures as non-fatal."""
    guest_module = importlib.import_module("captive_portal.guest_app")

    migration = AsyncMock(
        return_value=MigrationResult(
            omada_migrated=True,
            session_fields_migrated=3,
            guest_url_migrated=True,
        ),
    )
    monkeypatch.setattr("captive_portal.services.config_migration.migrate_yaml_to_db", migration)

    with caplog.at_level(logging.INFO, logger="captive_portal.guest"):
        await guest_module._run_config_migration(AppSettings(db_path=":memory:"), db_engine)

    assert "Omada settings migrated" in caplog.text
    assert "3 session fields migrated" in caplog.text
    assert "guest_external_url migrated" in caplog.text

    failure = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("captive_portal.services.config_migration.migrate_yaml_to_db", failure)
    with caplog.at_level(logging.WARNING, logger="captive_portal.guest"):
        await guest_module._run_config_migration(AppSettings(db_path=":memory:"), db_engine)

    assert "Config migration skipped" in caplog.text


@pytest.mark.asyncio
async def test_app_load_omada_config_returns_none_on_errors() -> None:
    """Admin Omada config loading degrades to None when DB access fails."""
    app_module = importlib.import_module("captive_portal.app")

    assert await app_module._load_omada_config(object()) is None


def test_create_app_loads_settings_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app calls AppSettings.load when settings are omitted."""
    app_module = importlib.import_module("captive_portal.app")

    settings = AppSettings(db_path=":memory:")
    monkeypatch.setattr(app_module.AppSettings, "load", staticmethod(lambda: settings))

    app = app_module.create_app()

    assert app.state.debug_guest_portal == settings.debug_guest_portal


def test_create_app_raises_when_static_themes_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_app fails fast when static theme assets are unavailable."""
    app_module = importlib.import_module("captive_portal.app")

    missing = tmp_path / "themes-does-not-exist"
    monkeypatch.setattr(app_module, "_THEMES_DIR", missing)

    with pytest.raises(RuntimeError, match="Static themes directory"):
        app_module.create_app(settings=AppSettings(db_path=":memory:"))


@pytest.mark.asyncio
async def test_app_lifespan_disposes_engine_on_init_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin lifespan disposes database resources when init_db fails."""
    app_module = importlib.import_module("captive_portal.app")

    disposed = False

    def fail_init(_engine: object) -> None:
        """Raise a synthetic database initialization failure."""
        raise RuntimeError("init failed")

    def dispose() -> None:
        """Record disposal."""
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(app_module, "create_db_engine", lambda _url: object())
    monkeypatch.setattr(app_module, "init_db", fail_init)
    monkeypatch.setattr(app_module, "dispose_engine", dispose)

    with _without_root_handlers():
        with pytest.raises(RuntimeError, match="init failed"):
            async with app_module._make_lifespan(AppSettings(db_path=":memory:"))(FastAPI()):
                pass

    assert disposed is True


def test_app_lifespan_logs_configured_omada(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Admin lifespan logs when Omada configuration is present."""
    app_module = importlib.import_module("captive_portal.app")

    monkeypatch.setattr(
        app_module,
        "_load_omada_config",
        AsyncMock(
            return_value=OmadaRuntimeConfig(
                selected_backend="legacy",
                selection_reason="test",
                base_url="https://omada.example",
                controller_id="",
                site_name="Default",
                verify_ssl=True,
                username="operator",
                password="secret",
            ),
        ),
    )
    monkeypatch.setattr(app_module.HAPoller, "start", AsyncMock())
    monkeypatch.setattr(app_module.HAPoller, "stop", AsyncMock())
    app = app_module.create_app(settings=AppSettings(db_path=":memory:"))

    with caplog.at_level(logging.INFO, logger="captive_portal"):
        with TestClient(app):
            assert app.state.omada_config.base_url == "https://omada.example"

    assert "Omada controller configured" in caplog.text


def test_create_guest_app_loads_settings_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_guest_app calls AppSettings.load when settings are omitted."""
    guest_module = importlib.import_module("captive_portal.guest_app")

    settings = AppSettings(db_path=":memory:", debug_guest_portal=True)
    monkeypatch.setattr(guest_module.AppSettings, "load", staticmethod(lambda: settings))

    app = guest_module.create_guest_app()

    assert app.state.debug_guest_portal is True


def test_mount_guest_static_raises_for_missing_directory(tmp_path: Path) -> None:
    """Guest static mounting fails fast for missing theme assets."""
    with pytest.raises(RuntimeError, match="Static themes directory"):
        mount_guest_static(FastAPI(), tmp_path / "missing-themes")


def test_guest_validation_exception_handler_renders_html() -> None:
    """Guest validation errors render friendly HTML error pages."""
    app = FastAPI()
    register_guest_exception_handlers(app)

    @app.get("/needs-int")
    async def needs_int(value: int) -> dict[str, int]:
        """Return the integer value when validation succeeds."""
        return {"value": value}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/needs-int", params={"value": "bad"})

    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]
    assert "There was a problem with your request" in response.text


@pytest.mark.asyncio
async def test_guest_debug_receive_wrapper_logs_other_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guest debug receive wrapper logs non-request ASGI messages."""

    async def receive() -> Message:
        """Return a non-request ASGI message."""
        return {"type": "lifespan.startup"}

    wrapped = DebugLoggingMiddleware._wrap_receive(receive, "GET", "/guest/authorize")

    with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
        message = await wrapped()

    assert message == {"type": "lifespan.startup"}
    assert "lifespan.startup" in caplog.text


@pytest.mark.asyncio
async def test_guest_lifespan_disposes_engine_on_init_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guest lifespan disposes database resources when init_db fails."""
    guest_module = importlib.import_module("captive_portal.guest_app")

    disposed = False

    def fail_init(_engine: object) -> None:
        """Raise a synthetic database initialization failure."""
        raise RuntimeError("guest init failed")

    def dispose() -> None:
        """Record disposal."""
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(guest_module, "create_db_engine", lambda _url: object())
    monkeypatch.setattr(guest_module, "init_db", fail_init)
    monkeypatch.setattr(guest_module, "dispose_engine", dispose)

    with _without_root_handlers():
        with pytest.raises(RuntimeError, match="guest init failed"):
            async with guest_module._make_guest_lifespan(AppSettings(db_path=":memory:"))(
                FastAPI()
            ):
                pass

    assert disposed is True


@pytest.mark.asyncio
async def test_guest_lifespan_loads_configured_omada(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guest lifespan stores and logs configured Omada runtime settings."""
    guest_module = importlib.import_module("captive_portal.guest_app")

    class _Result:
        """Result double with a first method."""

        def __init__(self, value: object | None) -> None:
            """Store the value to return."""
            self.value = value

        def first(self) -> object | None:
            """Return the configured value."""
            return self.value

    class _FakeSession:
        """Session double returning Omada then Portal config rows."""

        calls = 0

        def __init__(self, _engine: object) -> None:
            """Accept an engine argument."""

        def exec(self, _statement: object) -> _Result:
            """Return Omada config for first query and portal config for second."""
            type(self).calls += 1
            if type(self).calls == 1:
                return _Result(
                    OmadaConfig(
                        id=1,
                        controller_url="https://omada.example",
                        username="operator",
                        encrypted_password="ciphertext",
                    ),
                )
            return _Result(PortalConfig(id=1, guest_external_url="https://guest.example"))

        def close(self) -> None:
            """Close the fake session."""

    async def no_migration(_settings: AppSettings, _engine: object) -> None:
        """Skip migration for the fake database."""

    monkeypatch.setattr(guest_module, "create_db_engine", lambda _url: object())
    monkeypatch.setattr(guest_module, "init_db", lambda _engine: None)
    monkeypatch.setattr(guest_module, "dispose_engine", lambda: None)
    monkeypatch.setattr(guest_module, "_run_config_migration", no_migration)
    monkeypatch.setattr("sqlmodel.Session", _FakeSession)
    monkeypatch.setattr(
        "captive_portal.config.omada_config.build_omada_config",
        AsyncMock(return_value={"runtime": "omada"}),
    )
    app = FastAPI()

    with caplog.at_level(logging.INFO, logger="captive_portal.guest"):
        async with guest_module._make_guest_lifespan(AppSettings(db_path=":memory:"))(app):
            assert app.state.omada_config == {"runtime": "omada"}
            assert app.state.guest_external_url == "https://guest.example"

    assert "Omada controller configured" in caplog.text


@contextmanager
def _without_root_handlers() -> Iterator[None]:
    """Temporarily clear root logging handlers to exercise basicConfig."""
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    root.handlers.clear()
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.handlers.extend(old_handlers)
