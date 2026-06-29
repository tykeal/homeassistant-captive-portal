# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Focused coverage tests for API route endpoint branches."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.testclient import TestClient
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.api.routes import (
    admin_accounts,
    admin_auth,
    admin_login_ui,
    admin_logout_ui,
    audit_config,
    booking_authorize,
    captive_detect,
    dashboard_ui,
    grants,
    guest_portal,
    integrations,
    integrations_ui,
    omada_settings_helpers,
    omada_settings_ui,
    portal_settings_ui,
    vouchers,
    vouchers_bulk_ui,
)
from captive_portal.api.routes.integrations_helpers import parse_allowed_vlans
from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.admin_user import AdminRole, AdminUser
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.password_hashing import hash_password
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.voucher_service import (
    VoucherCollisionError,
    VoucherExpiredError,
    VoucherNotFoundError,
    VoucherRedeemedError,
)

_ADMIN_ID = UUID("00000000-0000-4000-8000-000000000001")


class _AuditRecorder:
    """Replacement audit service used to avoid unrelated persistence behavior."""

    def __init__(self, session: Session) -> None:
        """Accept the same session argument as the real audit service."""
        self.session = session
        self.calls: list[dict[str, Any]] = []

    async def log_admin_action(self, **kwargs: Any) -> None:
        """Record admin audit calls."""
        self.calls.append(kwargs)


class _VoucherServiceFactory:
    """Replacement voucher service with configurable create outcomes."""

    outcome: ClassVar[Voucher | Exception]
    seen_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, session: Session) -> None:
        """Accept the same session argument as the real voucher service."""
        self.session = session

    async def create(self, **kwargs: Any) -> Voucher:
        """Return the configured voucher or raise the configured exception."""
        self.__class__.seen_kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def admin_api_client(app: FastAPI, client: TestClient) -> TestClient:
    """Return a client with admin authentication overridden."""
    app.dependency_overrides[require_admin] = lambda: _ADMIN_ID
    return client


@pytest.fixture
def booking_client(db_session: Session) -> TestClient:
    """Return a minimal client for the legacy booking authorization route."""
    test_app = FastAPI()
    test_app.include_router(booking_authorize.router)

    def get_test_session() -> Generator[Session, None, None]:
        """Yield the existing test session for booking route requests."""
        yield db_session

    test_app.dependency_overrides[booking_authorize.get_db_session] = get_test_session
    return TestClient(test_app)


def _integration(
    db_session: Session,
    *,
    integration_id: str = "calendar.test",
    grace: int = 15,
) -> HAIntegrationConfig:
    """Persist and return an HA integration config."""
    integration = HAIntegrationConfig(
        integration_id=integration_id,
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=grace,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


def _event(
    db_session: Session,
    *,
    integration_id: str = "calendar.test",
    code: str = "1234",
    start_delta: timedelta = timedelta(minutes=-5),
    end_delta: timedelta = timedelta(hours=1),
) -> RentalControlEvent:
    """Persist and return a Rental Control event."""
    now = datetime.now(timezone.utc)
    event = RentalControlEvent(
        integration_id=integration_id,
        event_index=0,
        slot_code=code,
        start_utc=now + start_delta,
        end_utc=now + end_delta,
        raw_attributes="{}",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_voucher_api_validation_and_error_paths(
    admin_api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voucher API validates VLANs and maps service exceptions."""
    monkeypatch.setattr(vouchers, "VoucherService", _VoucherServiceFactory)
    monkeypatch.setattr(vouchers, "AuditService", _AuditRecorder)

    invalid_payloads = [
        {"duration_minutes": 60, "allowed_vlans": "10"},
        {"duration_minutes": 60, "allowed_vlans": [True]},
        {"duration_minutes": 60, "allowed_vlans": [4095]},
    ]
    for payload in invalid_payloads:
        response = admin_api_client.post("/api/vouchers/", json=payload)
        assert response.status_code == 422

    _VoucherServiceFactory.outcome = Voucher(
        code="ABC123",
        duration_minutes=60,
        status=VoucherStatus.UNUSED,
        allowed_vlans=[20, 10],
        max_devices=2,
    )
    response = admin_api_client.post(
        "/api/vouchers/",
        json={
            "duration_minutes": 60,
            "allowed_vlans": [20, 10, 20],
            "max_devices": 2,
        },
    )
    assert response.status_code == 201
    assert response.json()["allowed_vlans"] == [20, 10]
    assert _VoucherServiceFactory.seen_kwargs["allowed_vlans"] == [10, 20]

    _VoucherServiceFactory.outcome = VoucherCollisionError("collision")
    response = admin_api_client.post("/api/vouchers/", json={"duration_minutes": 60})
    assert response.status_code == 409

    _VoucherServiceFactory.outcome = ValueError("invalid duration")
    response = admin_api_client.post("/api/vouchers/", json={"duration_minutes": 60})
    assert response.status_code == 400


def test_integrations_api_crud_and_error_paths(
    admin_api_client: TestClient,
    app: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration API covers CRUD, discovery, validation, and misses."""
    monkeypatch.setattr(integrations, "AuditService", _AuditRecorder)

    for payload in (
        {"integration_id": "calendar.bad", "allowed_vlans": "10"},
        {"integration_id": "calendar.bad", "allowed_vlans": [False]},
        {"integration_id": "calendar.bad", "allowed_vlans": [5000]},
    ):
        assert admin_api_client.post("/api/integrations", json=payload).status_code == 422

    response = admin_api_client.post(
        "/api/integrations",
        json={
            "integration_id": "calendar.unit",
            "identifier_attr": "slot_code",
            "checkout_grace_minutes": 10,
            "allowed_vlans": [30, 20, 30],
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["allowed_vlans"] == [20, 30]
    config_id = created["id"]

    duplicate = admin_api_client.post(
        "/api/integrations",
        json={"integration_id": "calendar.unit"},
    )
    assert duplicate.status_code == 409

    assert admin_api_client.get("/api/integrations").json()[0]["integration_id"] == "calendar.unit"
    assert admin_api_client.get(f"/api/integrations/{config_id}").status_code == 200
    assert admin_api_client.get(f"/api/integrations/{uuid4()}").status_code == 404

    update = admin_api_client.patch(
        f"/api/integrations/{config_id}",
        json={"identifier_attr": "last_four", "checkout_grace_minutes": 20, "allowed_vlans": []},
    )
    assert update.status_code == 200
    assert update.json()["identifier_attr"] == "last_four"
    assert update.json()["allowed_vlans"] == []
    assert admin_api_client.patch(f"/api/integrations/{uuid4()}", json={}).status_code == 404
    assert (
        admin_api_client.patch(
            f"/api/integrations/{config_id}", json={"allowed_vlans": [0]}
        ).status_code
        == 422
    )

    if hasattr(app.state, "ha_client"):
        delattr(app.state, "ha_client")
    discovery = admin_api_client.get("/api/integrations/discover")
    assert discovery.status_code == 200
    assert discovery.json()["available"] is False

    delete_missing = admin_api_client.delete(f"/api/integrations/{uuid4()}")
    assert delete_missing.status_code == 404
    delete = admin_api_client.delete(f"/api/integrations/{config_id}")
    assert delete.status_code == 204
    assert db_session.get(HAIntegrationConfig, UUID(config_id)) is None


def test_booking_authorize_session_dependency(db_engine: Engine) -> None:
    """Legacy booking DB dependency raises until initialized and then yields."""
    booking_authorize._engine = None
    with pytest.raises(RuntimeError, match="not initialized"):
        next(booking_authorize.get_db_session())

    booking_authorize.set_db_engine(db_engine)
    generator = booking_authorize.get_db_session()
    session = next(generator)
    assert isinstance(session, Session)
    generator.close()
    booking_authorize._engine = None


def test_booking_authorize_endpoint_error_paths(
    booking_client: TestClient,
    db_session: Session,
) -> None:
    """Legacy booking authorization returns configured HTTP error paths."""
    no_integration = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "1234", "mac_address": "AA:BB:CC:DD:EE:FF"},
    )
    assert no_integration.status_code == 503

    _integration(db_session)
    not_found = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "1234", "mac_address": "AA:BB:CC:DD:EE:FF"},
    )
    assert not_found.status_code == 404

    _event(db_session, code="2222", start_delta=timedelta(hours=2), end_delta=timedelta(hours=3))
    early = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "2222", "mac_address": "AA:BB:CC:DD:EE:FF"},
    )
    assert early.status_code == 410
    assert "not started" in early.json()["detail"]

    _event(db_session, code="3333", start_delta=timedelta(hours=-3), end_delta=timedelta(hours=-2))
    ended = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "3333", "mac_address": "AA:BB:CC:DD:EE:FF"},
    )
    assert ended.status_code == 410
    assert "ended" in ended.json()["detail"]


def test_booking_authorize_success_and_duplicate(
    booking_client: TestClient,
    db_session: Session,
) -> None:
    """Legacy booking authorization creates and reuses an existing grant."""
    _integration(db_session)
    _event(db_session, code="1234")

    response = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "1234", "mac_address": "AA:BB:CC:DD:EE:FF"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Access granted successfully"

    duplicate = booking_client.post(
        "/api/guest/authorize",
        json={"booking_code": "1234", "mac_address": "11:22:33:44:55:66"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["grant_id"] == body["grant_id"]

    grant = db_session.get(AccessGrant, UUID(body["grant_id"]))
    assert grant is not None
    assert grant.booking_ref == "1234"


class _CSRFPass:
    """CSRF dependency replacement that always accepts tokens."""

    async def validate_token(self, request: Request) -> None:
        """Accept the submitted request token."""

    def generate_token(self) -> str:
        """Return a deterministic CSRF token."""
        return "csrf-token"

    def get_token_from_request(self, request: Request) -> str | None:
        """Return an existing token from cookies when present."""
        return request.cookies.get("csrftoken")

    def set_csrf_cookie(self, response: Any, token: str) -> None:
        """Set a test CSRF cookie on the response."""
        response.set_cookie("csrftoken", token)


class _CSRFFail(_CSRFPass):
    """CSRF dependency replacement that rejects validation."""

    async def validate_token(self, request: Request) -> None:
        """Raise the same HTTP error as a failed CSRF check."""
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad csrf")


class _BulkVoucherService:
    """Voucher service replacement with configurable bulk-operation results."""

    create_results: ClassVar[list[str | Exception]] = []
    revoke_results: ClassVar[dict[str, Exception | None]] = {}
    delete_results: ClassVar[dict[str, dict[str, str] | Exception]] = {}

    def __init__(self, **kwargs: Any) -> None:
        """Accept keyword arguments used by route constructors."""
        self.voucher_repo = self

    async def create(self, **kwargs: Any) -> Voucher:
        """Return the next configured voucher or raise its exception."""
        result = self.create_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return Voucher(code=result, duration_minutes=kwargs["duration_minutes"])

    def get_by_code(self, code: str) -> Voucher | None:
        """Return a revoked voucher only for codes prefixed with revoked."""
        if code.startswith("REVOKED"):
            return Voucher(code=code, duration_minutes=60, status=VoucherStatus.REVOKED)
        return None

    async def revoke(self, code: str) -> None:
        """Apply the configured revoke outcome for a voucher code."""
        error = self.revoke_results.get(code)
        if error is not None:
            raise error

    async def delete(self, code: str) -> dict[str, str]:
        """Apply the configured delete outcome for a voucher code."""
        result = self.delete_results.get(code, {})
        if isinstance(result, Exception):
            raise result
        return result


def _install_ui_overrides(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    csrf: _CSRFPass | _CSRFFail | None = None,
) -> None:
    """Install common admin, CSRF, and audit overrides for UI route tests."""
    app.dependency_overrides[require_admin] = lambda: _ADMIN_ID
    app.dependency_overrides[get_csrf_protection] = lambda: csrf or _CSRFPass()
    monkeypatch.setattr(vouchers_bulk_ui, "VoucherService", _BulkVoucherService)
    monkeypatch.setattr(vouchers_bulk_ui, "AuditService", _AuditRecorder)
    monkeypatch.setattr(integrations_ui, "AuditService", _AuditRecorder)


def test_voucher_bulk_ui_redirect_branches(
    admin_api_client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bulk voucher UI routes cover success, partial, and error redirects."""
    _install_ui_overrides(app, monkeypatch)

    _BulkVoucherService.create_results = ["CODE1", "CODE2"]
    response = admin_api_client.post(
        "/admin/vouchers/bulk-create",
        data={"count": "2", "duration_minutes": "60", "csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Created+2+vouchers+successfully" in response.headers["location"]

    _BulkVoucherService.create_results = ["CODE3", VoucherCollisionError("collision")]
    partial = admin_api_client.post(
        "/admin/vouchers/bulk-create",
        data={"count": "2", "duration_minutes": "60", "csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "Created+1+of+2+vouchers" in partial.headers["location"]

    _BulkVoucherService.create_results = [VoucherCollisionError("collision")]
    failed = admin_api_client.post(
        "/admin/vouchers/bulk-create",
        data={"count": "1", "duration_minutes": "60", "csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "Failed+to+generate" in failed.headers["location"]

    no_revoke = admin_api_client.post(
        "/admin/vouchers/bulk-revoke",
        data={"csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "No+vouchers+selected" in no_revoke.headers["location"]

    _BulkVoucherService.revoke_results = {
        "EXPIRED1": VoucherExpiredError("expired"),
        "MISSING1": VoucherNotFoundError("missing"),
        "OK1": None,
    }
    revoke = admin_api_client.post(
        "/admin/vouchers/bulk-revoke",
        data={"csrf_token": "csrf-token", "codes": ["REVOKED1", "EXPIRED1", "MISSING1", "OK1"]},
        follow_redirects=False,
    )
    assert "Revoked+1+vouchers" in revoke.headers["location"]
    assert "skipped+3" in revoke.headers["location"]

    no_delete = admin_api_client.post(
        "/admin/vouchers/bulk-delete",
        data={"csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "No+vouchers+selected" in no_delete.headers["location"]

    _BulkVoucherService.delete_results = {
        "REDEEMED1": VoucherRedeemedError("redeemed"),
        "MISSING2": VoucherNotFoundError("missing"),
        "OK2": {"status": "unused"},
    }
    delete = admin_api_client.post(
        "/admin/vouchers/bulk-delete",
        data={"csrf_token": "csrf-token", "codes": ["REDEEMED1", "MISSING2", "OK2"]},
        follow_redirects=False,
    )
    assert "Deleted+1+vouchers" in delete.headers["location"]
    assert "skipped+2" in delete.headers["location"]


def test_voucher_bulk_ui_csrf_failures(
    admin_api_client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bulk voucher UI routes redirect when CSRF validation fails."""
    _install_ui_overrides(app, monkeypatch, _CSRFFail())
    for path in ("bulk-revoke", "bulk-delete"):
        response = admin_api_client.post(
            f"/admin/vouchers/{path}",
            data={"csrf_token": "bad", "codes": "ABC123"},
            follow_redirects=False,
        )
        assert "Invalid+CSRF+token" in response.headers["location"]


def test_integrations_ui_save_and_delete_error_branches(
    admin_api_client: TestClient,
    app: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration UI routes cover CSRF, validation, missing, and delete paths."""
    _install_ui_overrides(app, monkeypatch, _CSRFFail())
    csrf_failure = admin_api_client.post(
        "/admin/integrations/save",
        data={"integration_id": "calendar.test", "checkout_grace_minutes": "5"},
        follow_redirects=False,
    )
    assert "Invalid+CSRF+token" in csrf_failure.headers["location"]

    _install_ui_overrides(app, monkeypatch)
    invalid_attr = admin_api_client.post(
        "/admin/integrations/save",
        data={"integration_id": "calendar.test", "checkout_grace_minutes": "5"},
        follow_redirects=False,
    )
    assert "identifier_attr" in invalid_attr.headers["location"]

    invalid_vlan = admin_api_client.post(
        "/admin/integrations/save",
        data={
            "integration_id": "calendar.test",
            "checkout_grace_minutes": "5",
            "identifier_attr": "slot_code",
            "allowed_vlans": "not-a-vlan",
        },
        follow_redirects=False,
    )
    assert "Invalid+VLAN+input" in invalid_vlan.headers["location"]

    missing_id = uuid4()
    missing_update = admin_api_client.post(
        "/admin/integrations/save",
        data={
            "id": str(missing_id),
            "integration_id": "calendar.test",
            "checkout_grace_minutes": "5",
            "identifier_attr": "slot_code",
        },
        follow_redirects=False,
    )
    assert "Integration+not+found" in missing_update.headers["location"]

    edit_missing = admin_api_client.get(f"/admin/integrations/edit/{missing_id}")
    assert edit_missing.status_code == 404

    delete_missing = admin_api_client.post(
        f"/admin/integrations/delete/{missing_id}",
        data={"csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "Integration+not+found" in delete_missing.headers["location"]

    integration = _integration(db_session, integration_id="calendar.delete")
    delete = admin_api_client.post(
        f"/admin/integrations/delete/{integration.id}",
        data={"csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert "Integration+deleted+successfully" in delete.headers["location"]

    _install_ui_overrides(app, monkeypatch, _CSRFFail())
    csrf_delete = admin_api_client.post(
        f"/admin/integrations/delete/{uuid4()}",
        data={"csrf_token": "bad"},
        follow_redirects=False,
    )
    assert "Invalid+CSRF+token" in csrf_delete.headers["location"]


def test_settings_current_admin_error_branches(db_session: Session) -> None:
    """Settings helpers reject missing and stale admin sessions."""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/settings",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )
    with pytest.raises(HTTPException) as missing:
        omada_settings_ui._get_current_admin(request, db_session)
    assert missing.value.status_code == 401

    request.state.admin_id = uuid4()
    with pytest.raises(HTTPException) as stale:
        portal_settings_ui.get_current_admin(request, db_session)
    assert stale.value.status_code == 401

    user = AdminUser(
        username="nonadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="nonadmin@example.com",
        role=AdminRole.VIEWER,
    )
    db_session.add(user)
    db_session.commit()
    request.state.admin_id = user.id
    assert omada_settings_ui._get_current_admin(request, db_session).id == user.id


class _CookieSessionConfig:
    """Minimal session config with the cookie name used by logout."""

    cookie_name = "sessionid"


class _SessionStoreRecorder:
    """Record deleted session IDs for logout branch assertions."""

    def __init__(self) -> None:
        """Initialize the deleted ID list."""
        self.deleted: list[str] = []

    def delete(self, session_id: str) -> None:
        """Record the deleted session ID."""
        self.deleted.append(session_id)


class _DashboardServiceError:
    """Dashboard service replacement that raises from both methods."""

    def __init__(self, session: Session) -> None:
        """Accept the session constructor argument."""
        self.session = session

    def get_stats(self) -> Any:
        """Raise a stats retrieval failure."""
        raise RuntimeError("stats failed")

    def get_recent_activity(self) -> Any:
        """Raise an activity retrieval failure."""
        raise RuntimeError("activity failed")


class _LegacyRuntimeClient:
    """Legacy runtime client used to cover RuntimeConfig legacy conversion."""

    def __init__(self, **kwargs: Any) -> None:
        """Accept legacy client keyword arguments."""
        self.kwargs = kwargs

    async def __aenter__(self) -> _LegacyRuntimeClient:
        """Enter the fake legacy client context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake legacy client context."""


class _GenericLegacyErrorClient(_LegacyRuntimeClient):
    """Legacy client that raises a non-Omada exception."""

    async def __aenter__(self) -> _GenericLegacyErrorClient:
        """Raise a generic connection error."""
        raise RuntimeError("unexpected")


def _grant_for_routes() -> AccessGrant:
    """Create a grant for direct route helper tests."""
    now = datetime.now(timezone.utc)
    return AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=now,
        end_utc=now + timedelta(hours=1),
    )


def _plain_request(
    path: str = "/",
    *,
    app_state: Any | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
    root_path: str = "",
) -> Request:
    """Build a plain HTTP request for direct route calls."""
    app = SimpleNamespace(state=app_state or SimpleNamespace())
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "root_path": root_path,
            "app": app,
        }
    )


@pytest.mark.asyncio
async def test_miscellaneous_route_branches(
    admin_api_client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """Miscellaneous route modules cover small remaining branches."""
    _install_ui_overrides(app, monkeypatch)
    monkeypatch.setattr(dashboard_ui, "DashboardService", _DashboardServiceError)
    dashboard = admin_api_client.get("/admin/dashboard/")
    assert dashboard.status_code == 200
    assert "csrftoken" in dashboard.headers.get("set-cookie", "")

    detect_request = _plain_request(
        app_state=SimpleNamespace(guest_external_url="https://guest.test")
    )
    assert captive_detect._resolve_redirect_base(detect_request) == "https://guest.test"

    login_request = _plain_request("/admin/login")
    login_request.state.admin_id = uuid4()
    login_response = await admin_login_ui.admin_login_page(login_request)
    assert login_response.status_code == 303

    store = _SessionStoreRecorder()
    logout_request = _plain_request(
        "/admin/logout",
        app_state=SimpleNamespace(session_store=store, session_config=_CookieSessionConfig()),
        headers=[(b"cookie", b"sessionid=cookie-session")],
    )
    logout_response = await admin_logout_ui.admin_logout(logout_request)
    assert logout_response.status_code == 303
    assert store.deleted == ["cookie-session"]

    audit_request = _plain_request()
    new_audit = audit_config._get_audit_config(audit_request).model_copy(
        update={"audit_retention_days": 14}
    )
    assert (await audit_config.get_audit_config(_ADMIN_ID, new_audit)).audit_retention_days == 14
    updated_audit = await audit_config.update_audit_config(new_audit, _ADMIN_ID, audit_request)
    assert updated_audit.audit_retention_days == 14

    csrf_response = Response()
    existing = await admin_auth.get_csrf_token(
        _plain_request(headers=[(b"cookie", b"csrftoken=existing-token")]),
        csrf_response,
        cast(CSRFProtection, _CSRFPass()),
    )
    assert existing["csrf_token"] == "existing-token"

    current = AdminUser(
        username="current",
        password_hash=hash_password("SecureP@ss123"),
        email="current@example.com",
        role=AdminRole.ADMIN,
    )
    other = AdminUser(
        username="other",
        password_hash=hash_password("SecureP@ss123"),
        email="other@example.com",
        role=AdminRole.ADMIN,
    )
    db_session.add(current)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(current)
    db_session.refresh(other)

    account_request = _plain_request()
    with pytest.raises(HTTPException) as invalid_session:
        admin_accounts.get_current_admin(account_request, db_session)
    assert invalid_session.value.status_code == 401
    account_request.state.admin_id = uuid4()
    with pytest.raises(HTTPException) as stale_session:
        admin_accounts.get_current_admin(account_request, db_session)
    assert stale_session.value.detail == "Invalid session"

    with pytest.raises(HTTPException) as update_missing:
        await admin_accounts.update_admin_account(
            account_request,
            uuid4(),
            admin_accounts.AdminAccountUpdate(email="new@example.com"),
            current,
            db_session,
            cast(CSRFProtection, _CSRFPass()),
        )
    assert update_missing.value.status_code == 404

    with pytest.raises(HTTPException) as duplicate_email:
        await admin_accounts.update_admin_account(
            account_request,
            current.id,
            admin_accounts.AdminAccountUpdate(email="other@example.com"),
            current,
            db_session,
            cast(CSRFProtection, _CSRFPass()),
        )
    assert duplicate_email.value.status_code == 409

    updated = await admin_accounts.update_admin_account(
        account_request,
        current.id,
        admin_accounts.AdminAccountUpdate(password="NewSecureP@ss123"),
        current,
        db_session,
        cast(CSRFProtection, _CSRFPass()),
    )
    assert updated.username == "current"

    with pytest.raises(HTTPException) as delete_missing:
        await admin_accounts.delete_admin_account(
            account_request,
            uuid4(),
            current,
            db_session,
            cast(CSRFProtection, _CSRFPass()),
        )
    assert delete_missing.value.status_code == 404


@pytest.mark.asyncio
async def test_grant_and_omada_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """Grant and Omada helpers cover remaining status and error branches."""

    class FailingRevokeAdapter:
        """Adapter stub that fails controller revocation."""

        async def revoke(self, **kwargs: Any) -> None:
            """Raise a controller error."""
            raise OmadaClientError("down")

    result = await grants._revoke_with_controller(FailingRevokeAdapter(), _grant_for_routes())  # type: ignore[arg-type]
    assert result.controller_error is not None

    now = datetime.now(timezone.utc)
    future_grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=now + timedelta(hours=1),
        end_utc=now + timedelta(hours=2),
    )
    expired_grant = AccessGrant(
        mac="11:22:33:44:55:66",
        device_id="11:22:33:44:55:66",
        start_utc=now - timedelta(hours=2),
        end_utc=now - timedelta(hours=1),
    )
    db_session.add(future_grant)
    db_session.add(expired_grant)
    db_session.commit()
    assert (
        await grants.get_grant(future_grant.id, db_session, _ADMIN_ID)
    ).status == GrantStatus.PENDING
    assert (
        await grants.get_grant(expired_grant.id, db_session, _ADMIN_ID)
    ).status == GrantStatus.EXPIRED

    legacy_runtime = OmadaRuntimeConfig(
        selected_backend="legacy",
        selection_reason="test",
        base_url="https://omada.test:8043",
        controller_id="0123456789ab",
        site_name="Default",
        verify_ssl=True,
        username="operator",
        password="secret",
    )
    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.base_client.OmadaClient",
        _LegacyRuntimeClient,
    )
    assert (
        await omada_settings_helpers.test_omada_connection(
            SimpleNamespace(omada_config=legacy_runtime)
        )
        == "connected"
    )

    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.base_client.OmadaClient",
        _GenericLegacyErrorClient,
    )
    assert (
        await omada_settings_helpers.test_omada_connection(
            SimpleNamespace(
                omada_config={
                    "base_url": "https://omada.test:8043",
                    "controller_id": "0123456789ab",
                    "username": "operator",
                    "password": "secret",
                }
            )
        )
        == "error"
    )


def test_direct_validation_helpers_cover_none_and_range() -> None:
    """Direct model validation covers None and range helper branches."""
    assert (
        vouchers.CreateVoucherRequest(duration_minutes=60, allowed_vlans=None).allowed_vlans is None
    )
    assert (
        integrations.IntegrationConfigCreate(
            integration_id="calendar.none",
            allowed_vlans=None,  # type: ignore[arg-type]
        ).allowed_vlans
        == []
    )
    assert (
        integrations.IntegrationConfigUpdate(
            checkout_grace_minutes=None, allowed_vlans=None
        ).allowed_vlans
        is None
    )
    with pytest.raises(ValueError, match="allowed_vlans must be a list"):
        integrations.IntegrationConfigUpdate.validate_vlans("10")  # type: ignore[arg-type]
    invalid_range = parse_allowed_vlans("0", "")
    assert isinstance(invalid_range, RedirectResponse)


def test_guest_portal_optional_session_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guest portal optional session handles uninitialized database runtime errors."""

    def raises_uninitialized() -> Generator[Session, None, None]:
        """Raise an uninitialized database runtime error."""
        raise RuntimeError("database not initialized")
        yield  # pragma: no cover - keeps this function a generator

    request = _plain_request("/guest/authorize")
    request.scope["query_string"] = b"code=ABCD&csrf_token=token"
    request.app.dependency_overrides = {get_session: raises_uninitialized}
    generator = guest_portal._get_optional_session(request)
    assert next(generator) is None
