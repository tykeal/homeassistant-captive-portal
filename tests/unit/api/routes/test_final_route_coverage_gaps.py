# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Focused tests for the final route coverage gaps."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.testclient import TestClient
from sqlmodel import Session

import captive_portal
from captive_portal.api.routes import (
    grants,
    grants_ui,
    guest_portal,
    integrations_ui,
    omada_settings_ui,
    portal_config,
    portal_settings_ui,
    vouchers_ui,
)
from captive_portal.api.routes.guest_authorization import (
    context as guest_context,
    controller as guest_controller,
    form as guest_form,
    orchestration as guest_orchestration,
)
from captive_portal.api.routes.vouchers_purge_ui import purge_confirm as _purge_confirm
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter
from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.admin_user import AdminRole, AdminUser
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.database import get_session
from captive_portal.security.csrf import CSRFProtection, get_csrf_protection
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.security.session_middleware import require_admin
from captive_portal.services.audit_service import AuditService
from captive_portal.services.grant_service import GrantOperationError
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import CodeType, UnifiedCodeService

_ADMIN_ID = UUID("00000000-0000-4000-8000-000000000200")


class _CSRFPass:
    """CSRF test double that accepts every request."""

    async def validate_token(self, request: Request) -> None:
        """Accept the submitted request."""

    def generate_token(self) -> str:
        """Return a deterministic token."""
        return "csrf-token"

    def get_token_from_request(self, request: Request) -> str | None:
        """Read a token from the request cookie."""
        return request.cookies.get("csrftoken")

    def set_csrf_cookie(self, response: Any, token: str) -> None:
        """Set a CSRF cookie on the response."""
        response.set_cookie("csrftoken", token)


class _CSRFFail(_CSRFPass):
    """CSRF test double that rejects every request."""

    async def validate_token(self, request: Request) -> None:
        """Raise the route-level CSRF failure."""
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad csrf")


class _AuditRecorder:
    """Audit service replacement that records calls in memory."""

    instances: list[_AuditRecorder] = []

    def __init__(self, session: Session | None = None) -> None:
        """Accept the route's optional session constructor argument."""
        self.session = session
        self.log_calls: list[dict[str, Any]] = []
        self.admin_calls: list[dict[str, Any]] = []
        self.__class__.instances.append(self)

    async def log(self, **kwargs: Any) -> None:
        """Record a guest audit call."""
        self.log_calls.append(kwargs)

    async def log_admin_action(self, **kwargs: Any) -> None:
        """Record an admin audit call."""
        self.admin_calls.append(kwargs)


class _GrantExtendOperationError:
    """Grant service replacement that rejects extensions."""

    def __init__(self, session: Session) -> None:
        """Accept the route's session constructor argument."""
        self.session = session

    async def extend(self, **kwargs: Any) -> AccessGrant:
        """Raise the grant operation error branch."""
        raise GrantOperationError("Cannot extend revoked grant")


class _GrantRevokeControllerError:
    """Grant service replacement that returns a revoked grant."""

    grant: AccessGrant

    def __init__(self, session: Session) -> None:
        """Accept the route's session constructor argument."""
        self.session = session

    async def revoke(self, **kwargs: Any) -> AccessGrant:
        """Return the configured revoked grant."""
        return self.__class__.grant


class _NoConfigResult:
    """Result object whose first row lookup is always empty."""

    def first(self) -> None:
        """Return no portal configuration row."""
        return None


class _FailingPortalConfigSession:
    """Session double that fails default portal config creation."""

    def __init__(self) -> None:
        """Initialize rollback tracking."""
        self.rolled_back = False

    def exec(self, statement: Any) -> _NoConfigResult:
        """Return an empty result for every statement."""
        return _NoConfigResult()

    def add(self, instance: Any) -> None:
        """Accept a pending instance."""

    def commit(self) -> None:
        """Fail the attempted default row commit."""
        raise RuntimeError("commit failed")

    def rollback(self) -> None:
        """Record that rollback was called."""
        self.rolled_back = True


class _NaiveExpiryVoucher:
    """Voucher-like row whose computed expiry is naive."""

    def __init__(self) -> None:
        """Initialize voucher-like fields with a fresh naive expiry."""
        self.code = "NAIVE0"
        self.status = VoucherStatus.ACTIVE
        self.is_activated_for_expiry = True
        self.expires_utc = datetime.now() + timedelta(minutes=30)
        self.redeemed_count = 1


class _VoucherExecResult:
    """Session exec result returning the voucher-like row."""

    def all(self) -> list[_NaiveExpiryVoucher]:
        """Return a single voucher-like row."""
        return [_NaiveExpiryVoucher()]


class _VoucherListSession:
    """Session double used for direct voucher list rendering."""

    def exec(self, statement: Any) -> _VoucherExecResult:
        """Return the fake query result."""
        return _VoucherExecResult()

    def commit(self) -> None:
        """Accept commit calls from the route."""


class _VoucherRepo:
    """Voucher repository double."""

    def __init__(self, session: Any) -> None:
        """Accept the route's session constructor argument."""
        self.session = session


class _GrantCountRepo:
    """Grant repository double returning no active devices."""

    def __init__(self, session: Any) -> None:
        """Accept the route's session constructor argument."""
        self.session = session

    def count_active_by_voucher_codes(self, codes: list[str]) -> dict[str, int]:
        """Return no active devices for the supplied codes."""
        return {}


class _NoExpireVoucherService:
    """Voucher service double that does not expire rows."""

    def __init__(self, **kwargs: Any) -> None:
        """Accept keyword arguments used by the route."""

    def expire_stale_vouchers(self, vouchers: list[Any]) -> int:
        """Return no expired vouchers."""
        return 0


class _NoPurgeService:
    """Voucher purge service double that does not purge rows."""

    def __init__(self, **kwargs: Any) -> None:
        """Accept keyword arguments used by the route."""

    async def auto_purge(self) -> int:
        """Return no purged vouchers."""
        return 0


class _TemplateStub:
    """Template double returning a plain HTML response."""

    def TemplateResponse(self, **kwargs: Any) -> Any:
        """Return a response with the template context attached."""
        response = cast(Any, HTMLResponse("rendered"))
        response.context = kwargs["context"]
        return response


def _request(
    path: str = "/",
    *,
    query_string: bytes = b"",
    app_state: Any | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
    method: str = "GET",
) -> Request:
    """Build a minimal request for direct route helper calls."""
    app = SimpleNamespace(
        state=app_state or SimpleNamespace(),
        dependency_overrides={},
    )
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "query_string": query_string,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "root_path": "",
            "app": app,
        }
    )


def _grant(status_value: GrantStatus = GrantStatus.ACTIVE) -> AccessGrant:
    """Create a basic access grant for route tests."""
    now = datetime.now(timezone.utc)
    return AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=now - timedelta(minutes=5),
        end_utc=now + timedelta(minutes=55),
        status=status_value,
    )


def _admin(role: AdminRole = AdminRole.ADMIN) -> AdminUser:
    """Create an admin model for direct route calls."""
    return AdminUser(
        username=f"user-{uuid4()}",
        password_hash="hashed",
        email=f"{uuid4()}@example.test",
        role=role,
    )


def _install_admin_overrides(app: FastAPI) -> None:
    """Install common admin and CSRF dependency overrides."""
    app.dependency_overrides[require_admin] = lambda: _ADMIN_ID
    app.dependency_overrides[get_csrf_protection] = lambda: _CSRFPass()
    app.dependency_overrides[get_omada_adapter] = lambda: None


def test_package_create_app_uses_lazy_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """The package-level create_app delegates to the lazy app factory."""
    app_module = importlib.import_module("captive_portal.app")

    def fake_factory() -> FastAPI:
        """Return a sentinel FastAPI application."""
        return FastAPI(title="lazy factory")

    monkeypatch.setattr(app_module, "create_app", fake_factory)

    assert captive_portal.create_app().title == "lazy factory"


def test_omada_settings_template_setup_is_available() -> None:
    """Omada settings module exposes template version wiring."""
    assert omada_settings_ui.templates.env.globals["app_version"]


@pytest.mark.asyncio
async def test_grants_api_remaining_error_branches(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grant API routes cover missing, active, conflict, and controller errors."""
    with pytest.raises(HTTPException) as missing:
        await grants.get_grant(uuid4(), db_session, _ADMIN_ID)
    assert missing.value.status_code == 404

    active_grant = _grant()
    db_session.add(active_grant)
    db_session.commit()
    db_session.refresh(active_grant)
    assert (await grants.get_grant(active_grant.id, db_session, _ADMIN_ID)).status == (
        GrantStatus.ACTIVE
    )

    monkeypatch.setattr(grants, "GrantService", _GrantExtendOperationError)
    with pytest.raises(HTTPException) as conflict:
        await grants.extend_grant(
            uuid4(),
            grants.ExtendGrantRequest(additional_minutes=5),
            _request("/api/grants/extend"),
            db_session,
            _ADMIN_ID,
            cast(CSRFProtection, _CSRFPass()),
        )
    assert conflict.value.status_code == 409

    revoked = _grant(GrantStatus.REVOKED)
    db_session.add(revoked)
    db_session.commit()
    db_session.refresh(revoked)
    _GrantRevokeControllerError.grant = revoked
    _AuditRecorder.instances.clear()
    monkeypatch.setattr(grants, "GrantService", _GrantRevokeControllerError)
    monkeypatch.setattr(grants, "AuditService", _AuditRecorder)

    async def controller_error(**kwargs: Any) -> grants.RevocationResult:
        """Return a controller error result."""
        return grants.RevocationResult(controller_error="controller down")

    monkeypatch.setattr(grants, "_revoke_with_controller", controller_error)
    response = await grants.revoke_grant(
        revoked.id,
        _request("/api/grants/revoke"),
        db_session,
        _ADMIN_ID,
        cast(CSRFProtection, _CSRFPass()),
        None,
    )
    assert response.controller_error == "controller down"
    assert _AuditRecorder.instances[-1].admin_calls[-1]["metadata"] == {
        "controller_error": "controller down"
    }


def test_grants_ui_remaining_redirect_branches(
    app: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grant UI routes cover failed status, CSRF cookie, and controller warnings."""
    _install_admin_overrides(app)
    assert grants_ui._recompute_status(_grant(GrantStatus.FAILED), datetime.now(timezone.utc)) == (
        "failed"
    )

    client = TestClient(app)
    list_response = client.get("/admin/grants/")
    assert list_response.status_code == 200
    assert "csrftoken" in list_response.headers.get("set-cookie", "")

    grant = _grant()
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    _AuditRecorder.instances.clear()
    monkeypatch.setattr(grants_ui, "AuditService", _AuditRecorder)

    async def controller_error(**kwargs: Any) -> grants.RevocationResult:
        """Return a controller error result."""
        return grants.RevocationResult(controller_error="controller down")

    monkeypatch.setattr(grants, "_revoke_with_controller", controller_error)
    revoke_response = client.post(
        f"/admin/grants/revoke/{grant.id}",
        data={"csrf_token": "csrf-token"},
        follow_redirects=False,
    )
    assert revoke_response.status_code == 303
    assert "Controller+revocation+failed" in revoke_response.headers["location"]
    assert _AuditRecorder.instances[-1].admin_calls[-1]["metadata"] == {
        "controller_error": "controller down"
    }


@pytest.mark.asyncio
async def test_guest_authorization_helpers_cover_failure_paths(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guest authorization helpers cover logging and controller-failure paths."""
    audit = _AuditRecorder()
    failed_grant = _grant(GrantStatus.FAILED)
    await guest_context.audit_controller_failure(
        audit_service=cast(AuditService, audit),
        request=_request(headers=[(b"user-agent", b"pytest")]),
        client_ip="192.0.2.5",
        mac_address="AA:BB:CC:DD:EE:FF",
        grant=failed_grant,
        error_detail="down",
    )
    assert audit.log_calls[-1]["meta"]["error"] == "controller_authorization_failed"

    legacy = OmadaLegacyAdapter(cast(Any, object()), site_id="Default")
    guest_controller.apply_legacy_site_override(legacy, "686982d482171c5562624ad1")
    assert legacy.site_id == "686982d482171c5562624ad1"

    with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
        guest_form.log_get_submission_debug(
            _request(
                "/guest/authorize",
                query_string=b"code=SECRET&csrf_token=TOKEN&clientMac=AA",
            )
        )
    assert "[REDACTED]" in caplog.text
    assert "SECRET" not in caplog.text
    assert "TOKEN" not in caplog.text

    request = _request(app_state=SimpleNamespace(debug_guest_portal=True))
    with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
        guest_orchestration._log_controller_start(request, None)
    assert "controller_auth_start" in caplog.text

    db_session.add(failed_grant)
    db_session.commit()
    db_session.refresh(failed_grant)

    async def failed_authorize(**kwargs: Any) -> tuple[AccessGrant, str]:
        """Return a failed controller grant."""
        return failed_grant, "controller down"

    monkeypatch.setattr(guest_orchestration, "authorize_with_controller", failed_authorize)
    dependencies = guest_context.GuestAuthorizationDependencies(
        rate_limiter=cast(RateLimiter, object()),
        unified_code_service=cast(UnifiedCodeService, object()),
        redirect_validator=cast(RedirectValidator, object()),
        session=db_session,
        audit_service=cast(AuditService, audit),
        portal_config=PortalConfig(id=1),
        omada_adapter=None,
    )
    decision = guest_context.AuthorizationDecisionResult(
        grant=failed_grant,
        code_type=CodeType.VOUCHER,
        target_type="voucher",
        target_id="CODE123",
    )
    flow_context = guest_context.GuestAuthorizationContext(
        client_ip="192.0.2.5",
        mac_address="AA:BB:CC:DD:EE:FF",
    )
    with pytest.raises(HTTPException) as controller_failure:
        await guest_orchestration._finalize_controller_authorization(
            request=_request(),
            omada_params=guest_context.GuestOmadaParams(),
            dependencies=dependencies,
            flow_context=flow_context,
            decision=decision,
        )
    assert controller_failure.value.status_code == 502


@pytest.mark.asyncio
async def test_guest_portal_fallback_and_submission_branches(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guest portal dependencies cover rollback, unavailable, and debug branches."""

    def raises_runtime_error() -> Generator[Session, None, None]:
        """Raise a non-initialization runtime error."""
        raise RuntimeError("unexpected database failure")
        yield  # pragma: no cover - keeps this function a generator

    request = _request(
        "/guest/authorize",
        query_string=b"code=CODE123&csrf_token=token",
    )
    request.app.dependency_overrides = {get_session: raises_runtime_error}
    optional_session = guest_portal._get_optional_session(request)
    with pytest.raises(RuntimeError, match="unexpected"):
        next(optional_session)

    failing_session = _FailingPortalConfigSession()
    with pytest.raises(HTTPException) as config_error:
        guest_portal.get_portal_config_dep(cast(Session, failing_session))
    assert config_error.value.status_code == 500
    assert failing_session.rolled_back is True

    with pytest.raises(HTTPException) as unavailable:
        await guest_portal.show_authorize_form(
            _request("/guest/authorize"),
            code="CODE123",
            csrf_token="token",
            session=None,
        )
    assert unavailable.value.status_code == 503

    async def handled_get_submission(**kwargs: Any) -> RedirectResponse:
        """Return a successful GET-submission redirect."""
        return RedirectResponse("/done", status_code=status.HTTP_303_SEE_OTHER)

    monkeypatch.setattr(guest_portal, "_handle_get_submission", handled_get_submission)
    debug_request = _request(
        "/guest/authorize",
        query_string=b"code=CODE123&csrf_token=token",
        app_state=SimpleNamespace(debug_guest_portal=True),
    )
    with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
        redirect = await guest_portal.show_authorize_form(
            debug_request,
            client_mac="AA:BB:CC:DD:EE:FF",
            code="CODE123",
            csrf_token="token",
            session=db_session,
        )
    assert redirect.status_code == 303
    assert "submission" in caplog.text


@pytest.mark.asyncio
async def test_integrations_and_settings_remaining_branches(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings routes cover unavailable discovery and authorization redirects."""
    discovery = await integrations_ui._run_discovery(
        _request(app_state=SimpleNamespace()),
        db_session,
    )
    assert discovery.available is False

    stale_request = _request("/admin/settings")
    stale_request.state.admin_id = uuid4()
    with pytest.raises(HTTPException) as omada_stale:
        omada_settings_ui._get_current_admin(stale_request, db_session)
    assert omada_stale.value.status_code == 401

    missing_request = _request("/admin/portal-settings")
    with pytest.raises(HTTPException) as portal_missing:
        portal_settings_ui.get_current_admin(missing_request, db_session)
    assert portal_missing.value.status_code == 401

    non_admin = _admin(AdminRole.VIEWER)
    portal_form = portal_settings_ui.PortalSettingsForm(
        csrf_token="csrf-token",
        rate_limit_attempts=5,
        rate_limit_window_seconds=60,
        success_redirect_url="/guest/welcome",
    )
    portal_non_admin = await portal_settings_ui.update_portal_settings(
        _request("/admin/portal-settings", app_state=SimpleNamespace()),
        db_session,
        non_admin,
        cast(CSRFProtection, _CSRFPass()),
        portal_form,
    )
    assert "Only+administrators" in portal_non_admin.headers["location"]

    portal_csrf = await portal_settings_ui.update_portal_settings(
        _request("/admin/portal-settings", app_state=SimpleNamespace()),
        db_session,
        _admin(),
        cast(CSRFProtection, _CSRFFail()),
        portal_form,
    )
    assert "Invalid+CSRF+token" in portal_csrf.headers["location"]

    omada_non_admin = await omada_settings_ui.update_omada_settings(
        _request("/admin/omada-settings", app_state=SimpleNamespace()),
        db_session,
        non_admin,
        cast(CSRFProtection, _CSRFPass()),
        "csrf-token",
    )
    assert "Only+administrators" in omada_non_admin.headers["location"]

    omada_csrf = await omada_settings_ui.update_omada_settings(
        _request("/admin/omada-settings", app_state=SimpleNamespace()),
        db_session,
        _admin(),
        cast(CSRFProtection, _CSRFFail()),
        "csrf-token",
    )
    assert "Invalid+CSRF+token" in omada_csrf.headers["location"]

    monkeypatch.setattr(omada_settings_ui, "encrypt_credential", lambda secret: f"enc:{secret}")
    monkeypatch.setattr(omada_settings_ui, "_rebuild_runtime_after_save", _async_none)
    _AuditRecorder.instances.clear()
    monkeypatch.setattr(omada_settings_ui, "AuditService", _AuditRecorder)
    saved = await omada_settings_ui.update_omada_settings(
        _request("/admin/omada-settings", app_state=SimpleNamespace()),
        db_session,
        _admin(),
        cast(CSRFProtection, _CSRFPass()),
        "csrf-token",
        controller_url="https://omada.example.test",
        client_id="client-id",
        client_secret="client-secret",
        client_secret_changed="true",
        openapi_mode="openapi",
        controller_id="0123456789ab",
        verify_ssl="true",
    )
    assert "success=Omada+controller" in saved.headers["location"]
    config = db_session.get(OmadaConfig, 1)
    assert config is not None
    assert config.encrypted_client_secret == "enc:client-secret"


async def _async_none(*args: Any, **kwargs: Any) -> None:
    """Return None from patched async helpers."""
    return None


@pytest.mark.asyncio
async def test_portal_config_update_branches(db_session: Session) -> None:
    """Portal config API covers stale admins and success redirect updates."""
    stale_request = _request("/api/admin/portal-config")
    stale_request.state.admin_id = uuid4()
    with pytest.raises(HTTPException) as stale:
        portal_config.get_current_admin(stale_request, db_session)
    assert stale.value.status_code == 401

    admin = _admin()
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    response = await portal_config.update_portal_config(
        portal_config.PortalConfigUpdate(
            success_redirect_url="/guest/done",
            rate_limit_attempts=None,
            rate_limit_window_seconds=None,
            session_idle_minutes=None,
            session_max_hours=None,
            guest_external_url=None,
        ),
        db_session,
        admin,
        _request("/api/admin/portal-config", app_state=SimpleNamespace()),
    )
    assert response.success_redirect_url == "/guest/done"


@pytest.mark.asyncio
async def test_voucher_ui_and_purge_remaining_branches(
    app: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voucher UI covers activated vouchers, CSRF cookie, and purge validation."""
    monkeypatch.setattr(vouchers_ui, "VoucherRepository", _VoucherRepo)
    monkeypatch.setattr(vouchers_ui, "AccessGrantRepository", _GrantCountRepo)
    monkeypatch.setattr(vouchers_ui, "VoucherService", _NoExpireVoucherService)
    monkeypatch.setattr(vouchers_ui, "VoucherPurgeService", _NoPurgeService)
    monkeypatch.setattr(vouchers_ui, "AuditService", _AuditRecorder)
    monkeypatch.setattr(vouchers_ui, "templates", _TemplateStub())
    direct_response = await vouchers_ui.get_vouchers(
        _request("/admin/vouchers"),
        cast(Session, _VoucherListSession()),
        _ADMIN_ID,
        cast(CSRFProtection, _CSRFPass()),
    )
    assert direct_response.status_code == 200
    _install_admin_overrides(app)
    voucher = Voucher(
        code="NAIVE1",
        duration_minutes=60,
        status=VoucherStatus.ACTIVE,
        redeemed_count=1,
        activated_utc=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(voucher)
    db_session.commit()

    client = TestClient(app)
    vouchers_response = client.get("/admin/vouchers/")
    assert vouchers_response.status_code == 200
    assert "csrftoken" in vouchers_response.headers.get("set-cookie", "")

    purge_response = client.post(
        "/admin/vouchers/purge-confirm",
        data={"csrf_token": "csrf-token", "min_age_days": "-1"},
        follow_redirects=False,
    )
    assert purge_response.status_code == 303
    assert "Age+threshold" in purge_response.headers["location"]

    direct_request = _request(
        "/admin/vouchers/purge-confirm",
        app_state=SimpleNamespace(),
    )
    response = await _purge_confirm(
        direct_request,
        db_session,
        _ADMIN_ID,
        cast(CSRFProtection, _CSRFFail()),
    )
    assert "Invalid+CSRF+token" in response.headers["location"]
