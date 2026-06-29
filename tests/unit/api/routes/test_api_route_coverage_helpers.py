# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Focused coverage tests for API route helper branches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from captive_portal.api.routes import audit_config, health, omada_settings_helpers
from captive_portal.api.routes.guest_authorization import bookings, context, controller
from captive_portal.api.routes.guest_authorization.context import (
    AuthorizationDecisionResult,
    GuestDecisionContext,
    GuestOmadaParams,
)
from captive_portal.api.routes.guest_authorization.orchestration import (
    _dispatch_authorization_decision,
    _resolve_omada_adapter,
)
from captive_portal.api.routes.guest_authorization.vouchers import authorize_voucher
from captive_portal.api.routes.integrations_helpers import (
    IntegrationSaveData,
    create_integration_record,
    parse_allowed_vlans,
)
from captive_portal.api.routes.omada_settings_helpers import OmadaFormData
from captive_portal.api.routes.vouchers_common import (
    BulkResult,
    format_bulk_message,
    parse_bulk_create_form,
    parse_vlan_form_input,
)
from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher
from captive_portal.services.audit_service import AuditService
from captive_portal.services.booking_code_validator import (
    BookingNotFoundError,
    BookingOutsideWindowError,
    DuplicateGrantError,
    IntegrationUnavailableError,
)
from captive_portal.services.unified_code_service import CodeType, CodeValidationResult
from captive_portal.services.voucher_service import (
    VoucherDeviceLimitError,
    VoucherRedemptionError,
)


class _AuditRecorder:
    """Record audit log calls made by route helper functions."""

    def __init__(self) -> None:
        """Initialize the call list."""
        self.calls: list[dict[str, Any]] = []

    async def log(self, **kwargs: Any) -> None:
        """Record a generic audit call."""
        self.calls.append(kwargs)

    async def log_admin_action(self, **kwargs: Any) -> None:
        """Record an admin audit call."""
        self.calls.append(kwargs)


class _MappingForm(dict[str, Any]):
    """Dictionary form object with a Starlette-like getlist method."""

    def getlist(self, key: str) -> list[Any]:
        """Return a list value for form keys that support multiples."""
        value = self.get(key, [])
        return list(value) if isinstance(value, list) else [value]


class _RateLimiterDenied:
    """Rate limiter stub that always denies the client."""

    def is_allowed(self, client_ip: str) -> bool:
        """Return false to exercise the denial branch."""
        return False

    def get_retry_after_seconds(self, client_ip: str) -> int:
        """Return the retry-after value used by the HTTP response."""
        return 42


class _CodeServiceError:
    """Unified code service stub that rejects submitted codes."""

    async def validate_code(self, code: str) -> CodeValidationResult:
        """Raise the validation error expected by the route helper."""
        raise ValueError("bad code")


class _OpenApiSuccessClient:
    """OpenAPI client stub that successfully obtains a token."""

    def __init__(self, **kwargs: Any) -> None:
        """Accept the same keyword arguments as the real client."""
        self.kwargs = kwargs

    async def get_access_token(self) -> str:
        """Return a fake access token."""
        return "token"


class _OpenApiErrorClient(_OpenApiSuccessClient):
    """OpenAPI client stub that raises a controller error."""

    async def get_access_token(self) -> str:
        """Raise the controller error handled by the helper."""
        raise OmadaClientError("denied")


class _LegacyContextClient:
    """Legacy client stub with async context manager support."""

    def __init__(self, **kwargs: Any) -> None:
        """Store construction arguments for assertions if needed."""
        self.kwargs = kwargs

    async def __aenter__(self) -> _LegacyContextClient:
        """Enter the fake legacy client context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake legacy client context."""


class _LegacyErrorClient(_LegacyContextClient):
    """Legacy client stub that fails while entering the context."""

    async def __aenter__(self) -> _LegacyErrorClient:
        """Raise a controller error on connection."""
        raise OmadaClientError("legacy failed")


class _FakeVoucherRepo:
    """Voucher repository stub used by voucher authorization tests."""

    def __init__(self, voucher: Voucher | None) -> None:
        """Store the voucher returned by code lookup."""
        self.voucher = voucher

    def get_by_code(self, code: str) -> Voucher | None:
        """Return the configured voucher regardless of code."""
        return self.voucher


class _VoucherServiceFactory:
    """Factory class replacing VoucherService for helper branch tests."""

    error: Exception | None = None
    voucher: Voucher | None = None
    grant: AccessGrant | None = None

    def __init__(self, session: Session) -> None:
        """Accept the route helper's session argument."""
        self.voucher_repo = _FakeVoucherRepo(self.voucher)

    async def redeem(self, code: str, mac: str) -> AccessGrant:
        """Return or raise the configured voucher redemption outcome."""
        if self.error is not None:
            raise self.error
        if self.grant is None:
            msg = "grant not configured"
            raise AssertionError(msg)
        return self.grant


def _request(
    *,
    headers: dict[str, str] | None = None,
    query_string: bytes = b"",
    debug: bool = False,
) -> Request:
    """Build a Starlette request with the fields used by route helpers."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/guest/authorize",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": query_string,
        "server": ("testserver", 80),
        "client": ("198.51.100.7", 12345),
        "scheme": "http",
        "root_path": "",
        "app": SimpleNamespace(state=SimpleNamespace(debug_guest_portal=debug)),
    }
    return Request(scope)


def _grant(*, status_value: GrantStatus = GrantStatus.PENDING) -> AccessGrant:
    """Create an access grant suitable for route helper tests."""
    now = datetime.now(timezone.utc)
    return AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=now,
        end_utc=now + timedelta(hours=1),
        status=status_value,
    )


def _validation(code_type: CodeType = CodeType.BOOKING) -> CodeValidationResult:
    """Create a reusable code validation result."""
    return CodeValidationResult(
        code_type=code_type,
        normalized_code="ABC123",
        original_code="abc123",
    )


def _decision_context(
    audit: _AuditRecorder | None = None, vid: str | None = None
) -> GuestDecisionContext:
    """Create a guest decision context with a fake audit service."""
    return GuestDecisionContext(
        request=_request(headers={"User-Agent": "pytest"}),
        audit_service=cast(AuditService, audit or _AuditRecorder()),
        client_ip="198.51.100.7",
        mac_address="AA:BB:CC:DD:EE:FF",
        vid=vid,
    )


def test_validate_omada_form_rejects_edge_cases() -> None:
    """Omada validation reports legacy and OpenAPI form errors."""
    with pytest.raises(TypeError, match="legacy Omada validation"):
        omada_settings_helpers.validate_omada_form("https://omada.test")

    def make_form(**overrides: str | bool) -> OmadaFormData:
        """Build typed Omada form data for validation assertions."""
        values: dict[str, str | bool] = {
            "controller_url": "https://omada.test:8043",
            "username": "operator",
            "client_id": "client-id",
            "controller_id": "0123456789ab",
            "password": "secret",
            "password_changed": "true",
            "openapi_mode": "openapi",
            "client_secret": "secret",
            "client_secret_changed": "true",
            "client_secret_exists": False,
        }
        values.update(overrides)
        return OmadaFormData(
            controller_url=cast(str, values["controller_url"]),
            username=cast(str, values["username"]),
            client_id=cast(str, values["client_id"]),
            controller_id=cast(str, values["controller_id"]),
            password=cast(str, values["password"]),
            password_changed=cast(str, values["password_changed"]),
            openapi_mode=cast(str, values["openapi_mode"]),
            client_secret=cast(str, values["client_secret"]),
            client_secret_changed=cast(str, values["client_secret_changed"]),
            client_secret_exists=cast(bool, values["client_secret_exists"]),
        )

    assert (
        omada_settings_helpers.validate_omada_form(make_form(openapi_mode="bad"))
        == "Backend mode must be auto, openapi, or legacy"
    )
    assert (
        omada_settings_helpers.validate_omada_form(make_form(username="", openapi_mode="legacy"))
        == "Username is required when controller URL is set"
    )
    assert (
        omada_settings_helpers.validate_omada_form(make_form(controller_id="not-hex"))
        == "Controller ID must be a hex string (12-64 characters)"
    )
    assert (
        omada_settings_helpers.validate_omada_form(make_form(password="", openapi_mode="legacy"))
        == "Password is required when setting up a new connection"
    )
    assert (
        omada_settings_helpers.validate_omada_form(make_form(client_id=""))
        == "Client ID is required for OpenAPI mode"
    )
    assert (
        omada_settings_helpers.validate_omada_form(
            make_form(client_secret="", client_secret_exists=False)
        )
        == "Client Secret is required for OpenAPI mode"
    )


@pytest.mark.asyncio
async def test_omada_connection_handles_runtime_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omada connection testing covers OpenAPI and legacy outcomes."""
    runtime = OmadaRuntimeConfig(
        selected_backend="openapi",
        selection_reason="test",
        base_url="https://omada.test:8043",
        controller_id="0123456789ab",
        site_name="Default",
        verify_ssl=True,
        client_id="cid",
        client_secret="secret",
    )
    state = SimpleNamespace(omada_config=runtime)

    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.openapi_client.OpenApiClient",
        _OpenApiSuccessClient,
    )
    assert await omada_settings_helpers.test_omada_connection(state) == "connected"

    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.openapi_client.OpenApiClient",
        _OpenApiErrorClient,
    )
    assert await omada_settings_helpers.test_omada_connection(state) == "error"

    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.base_client.OmadaClient",
        _LegacyContextClient,
    )
    state.omada_config = {
        "base_url": "https://omada.test:8043",
        "controller_id": "0123456789ab",
        "username": "operator",
        "password": "secret",
        "verify_ssl": False,
    }
    assert await omada_settings_helpers.test_omada_connection(state) == "connected"

    monkeypatch.setattr(
        "captive_portal.controllers.tp_omada.base_client.OmadaClient",
        _LegacyErrorClient,
    )
    assert await omada_settings_helpers.test_omada_connection(state) == "error"


@pytest.mark.asyncio
async def test_rebuild_runtime_after_save_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime rebuild reports builder, empty config, and connection failures."""
    config = OmadaConfig(id=1, controller_url="https://omada.test:8043")
    state = SimpleNamespace(grant_expiry_service=SimpleNamespace(omada_config="old"))

    async def no_runtime(config: OmadaConfig, logger: Any) -> None:
        """Return no runtime config from the fake builder."""
        return None

    monkeypatch.setattr("captive_portal.config.omada_config.build_omada_config", no_runtime)
    assert await omada_settings_helpers.rebuild_runtime_after_save(config, state) == (
        omada_settings_helpers.OMADA_CONFIGURATION_ERROR
    )
    assert state.omada_config is None
    assert state.grant_expiry_service.omada_config is None

    async def runtime(config: OmadaConfig, logger: Any) -> object:
        """Return a fake runtime config from the fake builder."""
        return object()

    async def connection_error(app_state: Any) -> str:
        """Return an Omada connection failure result."""
        return "error"

    monkeypatch.setattr("captive_portal.config.omada_config.build_omada_config", runtime)
    assert (
        await omada_settings_helpers.rebuild_runtime_after_save(config, state, connection_error)
        == omada_settings_helpers.OMADA_CONNECTION_ERROR
    )

    async def raises(config: OmadaConfig, logger: Any) -> object:
        """Raise a builder failure from the fake builder."""
        raise RuntimeError("boom")

    monkeypatch.setattr("captive_portal.config.omada_config.build_omada_config", raises)
    assert await omada_settings_helpers.rebuild_runtime_after_save(config, state) == (
        omada_settings_helpers.OMADA_CONFIGURATION_ERROR
    )


def test_voucher_common_parses_errors_and_messages() -> None:
    """Voucher form helpers cover invalid values and bulk messages."""
    assert parse_vlan_form_input(None) is None
    assert parse_vlan_form_input("20, 10, 20") == [10, 20]
    with pytest.raises(ValueError, match="Invalid VLAN ID"):
        parse_vlan_form_input("0")

    invalid_forms = [
        {"count": "abc"},
        {"count": "101"},
        {"count": "1", "duration_minutes": "bad"},
        {"count": "1", "duration_minutes": "0"},
        {"count": "1", "duration_minutes": "60", "max_devices": "bad"},
        {"count": "1", "duration_minutes": "60", "max_devices": "0"},
        {"count": "1", "duration_minutes": "60", "allowed_vlans": "4095"},
        {
            "count": "1",
            "duration_minutes": "60",
            "booking_ref": "B" * 129,
        },
    ]
    for form in invalid_forms:
        result = parse_bulk_create_form(_MappingForm(form), "")
        assert isinstance(result, RedirectResponse)
        assert result.status_code == status.HTTP_303_SEE_OTHER

    partial_msg, partial_key = format_bulk_message(
        BulkResult("deleted", success_count=1, skip_reasons={"not found": 2})
    )
    assert partial_key == "success"
    assert "skipped 2" in partial_msg
    error_msg, error_key = format_bulk_message(
        BulkResult("revoked", success_count=0, skip_reasons={"expired": 1})
    )
    assert error_key == "error"
    assert "No vouchers revoked" in error_msg


@pytest.mark.asyncio
async def test_integration_helper_create_duplicate_and_parse(
    db_session: Session,
) -> None:
    """Integration helpers cover duplicate creation and VLAN parse failures."""
    integration = HAIntegrationConfig(integration_id="calendar.test")
    db_session.add(integration)
    db_session.commit()

    duplicate = await create_integration_record(
        db_session,
        cast(AuditService, _AuditRecorder()),
        uuid4(),
        IntegrationSaveData("calendar.test", IdentifierAttr.SLOT_CODE, 15, [10]),
        "/root",
    )
    assert isinstance(duplicate, RedirectResponse)
    assert "Integration+already+exists" in duplicate.headers["location"]

    parsed = parse_allowed_vlans("30, 20, 30", "")
    assert parsed == [20, 30]
    invalid = parse_allowed_vlans("not-a-number", "")
    assert isinstance(invalid, RedirectResponse)
    assert "Invalid+VLAN+input" in invalid.headers["location"]


def test_audit_config_initializes_and_updates() -> None:
    """Audit configuration route helpers initialize and replace state."""
    request = _request()
    config = audit_config._get_audit_config(request)
    assert config.audit_retention_days == 30

    replacement = config.model_copy(update={"audit_retention_days": 45})
    request.app.state.audit_config = replacement
    assert audit_config._get_audit_config(request).audit_retention_days == 45


@pytest.mark.asyncio
async def test_health_readiness_handles_database_errors() -> None:
    """Readiness returns degraded status when the DB query raises."""

    class FailingSession:
        """Session stub that raises a SQLAlchemy error."""

        def __init__(self) -> None:
            """Initialize rollback tracking."""
            self.rolled_back = False

        def execute(self, statement: object) -> object:
            """Raise a database connectivity failure."""
            raise SQLAlchemyError("down")

        def rollback(self) -> None:
            """Record that rollback was called."""
            self.rolled_back = True

    response = Response()
    session = FailingSession()
    result = health.readiness_check(response=response, session=session)  # type: ignore[arg-type]
    assert response.status_code == 503
    assert result.status == "degraded"
    assert result.checks == {"database": "unavailable"}
    assert session.rolled_back is True
    assert (await health.health_check()).status == "ok"
    assert (await health.liveness_check()).status == "ok"


def test_booking_window_and_duplicate_branches(db_session: Session) -> None:
    """Booking helpers reject early, ended, and duplicate grants."""
    now = datetime.now(timezone.utc)
    with pytest.raises(BookingOutsideWindowError, match="begins"):
        bookings._check_booking_window(now + timedelta(hours=2), now + timedelta(hours=3), 0, now)
    with pytest.raises(BookingOutsideWindowError, match="ended"):
        bookings._check_booking_window(now - timedelta(hours=3), now - timedelta(hours=2), 0, now)
    assert bookings._check_booking_window(now - timedelta(minutes=1), now, 15, now) > now

    grant = _grant(status_value=GrantStatus.ACTIVE)
    grant.booking_ref = "ABC123"
    db_session.add(grant)
    db_session.commit()
    with pytest.raises(DuplicateGrantError):
        bookings._ensure_no_duplicate_grant(
            session=db_session,
            mac_address="AA:BB:CC:DD:EE:FF",
            normalized_code="abc123",
        )


def test_booking_match_errors_and_debug_logs(db_session: Session) -> None:
    """Booking lookup and debug helpers cover unavailable and not-found paths."""
    with pytest.raises(IntegrationUnavailableError):
        bookings._find_booking_match(db_session, "ABC123")

    db_session.add(HAIntegrationConfig(integration_id="calendar.test"))
    db_session.commit()
    with pytest.raises(BookingNotFoundError):
        bookings._find_booking_match(db_session, "ABC123")

    event = RentalControlEvent(
        integration_id="calendar.test",
        event_index=0,
        slot_code="1234",
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime.now(timezone.utc) + timedelta(hours=1),
        raw_attributes="{}",
    )
    match = bookings._BookingMatch(event=event, integration=HAIntegrationConfig(integration_id="x"))
    debug_request = _request(debug=True)
    bookings._log_booking_found(debug_request, match)
    bookings._log_grant_created(debug_request, _grant())


@pytest.mark.asyncio
async def test_booking_vlan_denial_is_audited() -> None:
    """Booking VLAN validation audits and rejects disallowed VLANs."""
    audit = _AuditRecorder()
    integration = HAIntegrationConfig(integration_id="calendar.test", allowed_vlans=[10])
    with pytest.raises(HTTPException) as exc_info:
        await bookings._validate_booking_vlan(
            decision_context=_decision_context(audit, vid="20"),
            validation_result=_validation(),
            integration=integration,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert audit.calls[0]["meta"]["error"] == "vlan_check_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised", "expected_status"),
    [
        (BookingNotFoundError("missing"), status.HTTP_404_NOT_FOUND),
        (BookingOutsideWindowError("outside"), status.HTTP_403_FORBIDDEN),
        (DuplicateGrantError("duplicate"), status.HTTP_409_CONFLICT),
        (IntegrationUnavailableError("unavailable"), status.HTTP_503_SERVICE_UNAVAILABLE),
    ],
)
async def test_authorize_booking_maps_helper_errors(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    raised: Exception,
    expected_status: int,
) -> None:
    """Booking authorization maps domain errors to HTTP responses."""

    def fail_find(session: Session, normalized_code: str) -> bookings._BookingMatch:
        """Raise the parametrized domain error."""
        raise raised

    audit = _AuditRecorder()
    monkeypatch.setattr(bookings, "_find_booking_match", fail_find)
    with pytest.raises(HTTPException) as exc_info:
        await bookings.authorize_booking(
            validation_result=_validation(),
            session=db_session,
            decision_context=_decision_context(audit),
        )
    assert exc_info.value.status_code == expected_status
    assert audit.calls


@pytest.mark.asyncio
async def test_context_denials_and_success_audit() -> None:
    """Guest context helpers audit rate, MAC, code, and success paths."""
    audit = _AuditRecorder()
    with pytest.raises(HTTPException) as rate_exc:
        await context.enforce_rate_limit(
            rate_limiter=_RateLimiterDenied(),  # type: ignore[arg-type]
            audit_service=audit,  # type: ignore[arg-type]
            request=_request(headers={"User-Agent": "pytest"}),
            client_ip="198.51.100.7",
        )
    assert rate_exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rate_exc.value.headers == {"Retry-After": "42"}

    with pytest.raises(HTTPException):
        await context.extract_authorization_mac(
            request=_request(),
            form_mac=None,
            audit_service=audit,  # type: ignore[arg-type]
            client_ip="198.51.100.7",
        )

    with pytest.raises(HTTPException) as code_exc:
        await context.validate_guest_code(
            code="bad",
            service=_CodeServiceError(),  # type: ignore[arg-type]
            audit_service=audit,  # type: ignore[arg-type]
            request=_request(headers={"User-Agent": "pytest"}),
            client_ip="198.51.100.7",
            mac_address="AA:BB:CC:DD:EE:FF",
        )
    assert code_exc.value.status_code == status.HTTP_400_BAD_REQUEST

    decision = AuthorizationDecisionResult(
        grant=_grant(status_value=GrantStatus.ACTIVE),
        code_type=CodeType.VOUCHER,
        target_type="voucher",
        target_id="ABC123",
        vlan_meta={"vlan_allowed": True},
    )
    await context.audit_success(
        audit_service=audit,  # type: ignore[arg-type]
        request=_request(headers={"User-Agent": "pytest"}),
        client_ip="198.51.100.7",
        mac_address="AA:BB:CC:DD:EE:FF",
        decision=decision,
    )
    assert audit.calls[-1]["outcome"] == "success"
    assert audit.calls[-1]["meta"]["vlan_allowed"] is True


@pytest.mark.asyncio
async def test_orchestration_dispatch_and_adapter_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestration helpers cover fallback and invalid-code branches."""
    request = _request()

    def factory_with_request(request: Request) -> None:
        """Factory accepting the request returns no adapter."""
        return None

    def factory_without_request() -> None:
        """Factory without request exercises TypeError fallback."""
        return None

    assert _resolve_omada_adapter(factory_with_request, request) is None
    assert _resolve_omada_adapter(factory_without_request, request) is None

    flow_context = context.GuestAuthorizationContext(client_ip="198.51.100.7")
    dependencies = context.GuestAuthorizationDependencies(
        rate_limiter=Mock(),
        unified_code_service=Mock(),
        redirect_validator=Mock(),
        session=Mock(),
        audit_service=_AuditRecorder(),  # type: ignore[arg-type]
        portal_config=PortalConfig(id=1),
        omada_adapter=None,
    )
    with pytest.raises(HTTPException) as none_exc:
        await _dispatch_authorization_decision(
            request=request,
            omada_params=GuestOmadaParams(),
            dependencies=dependencies,
            flow_context=flow_context,
        )
    assert none_exc.value.status_code == status.HTTP_400_BAD_REQUEST

    flow_context.validation_result = _validation(CodeType.INVALID)
    flow_context.mac_address = "AA:BB:CC:DD:EE:FF"
    with pytest.raises(HTTPException) as invalid_exc:
        await _dispatch_authorization_decision(
            request=request,
            omada_params=GuestOmadaParams(),
            dependencies=dependencies,
            flow_context=flow_context,
        )
    assert invalid_exc.value.detail == "Invalid code type"


@pytest.mark.asyncio
async def test_voucher_authorization_denial_paths(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """Voucher authorization audits VLAN, device-limit, and redemption failures."""
    voucher = Voucher(
        code="ABC123",
        duration_minutes=60,
        allowed_vlans=[10],
        max_devices=1,
    )
    audit = _AuditRecorder()
    _VoucherServiceFactory.voucher = voucher
    _VoucherServiceFactory.error = None
    _VoucherServiceFactory.grant = _grant(status_value=GrantStatus.ACTIVE)
    monkeypatch.setattr(
        "captive_portal.api.routes.guest_authorization.vouchers.VoucherService",
        _VoucherServiceFactory,
    )

    with pytest.raises(HTTPException) as vlan_exc:
        await authorize_voucher(
            validation_result=_validation(CodeType.VOUCHER),
            session=db_session,
            decision_context=_decision_context(audit, vid="20"),
        )
    assert vlan_exc.value.status_code == status.HTTP_403_FORBIDDEN

    _VoucherServiceFactory.voucher = None
    _VoucherServiceFactory.error = VoucherDeviceLimitError("too many")
    with pytest.raises(HTTPException) as limit_exc:
        await authorize_voucher(
            validation_result=_validation(CodeType.VOUCHER),
            session=db_session,
            decision_context=_decision_context(audit),
        )
    assert limit_exc.value.status_code == status.HTTP_410_GONE

    _VoucherServiceFactory.error = VoucherRedemptionError("expired")
    with pytest.raises(HTTPException) as redemption_exc:
        await authorize_voucher(
            validation_result=_validation(CodeType.VOUCHER),
            session=db_session,
            decision_context=_decision_context(audit),
        )
    assert redemption_exc.value.detail == "expired"


@pytest.mark.asyncio
async def test_controller_authorization_error_branch() -> None:
    """Controller helper marks grants failed when adapter authorization fails."""

    class FailingAdapter:
        """Adapter stub raising an Omada client error."""

        async def authorize(self, **kwargs: Any) -> dict[str, str]:
            """Raise an Omada client error."""
            raise OmadaClientError("controller down")

    grant, detail = await controller.authorize_with_controller(
        FailingAdapter(),  # type: ignore[arg-type]
        _grant(),
        "AA:BB:CC:DD:EE:FF",
    )
    assert grant.status == GrantStatus.FAILED
    assert detail is not None
