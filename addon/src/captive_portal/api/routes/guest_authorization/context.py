# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Context objects and shared steps for guest authorization flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.portal_config import PortalConfig
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.services.audit_service import AuditService
from captive_portal.services.redirect_validator import RedirectValidator
from captive_portal.services.unified_code_service import (
    CodeType,
    CodeValidationResult,
    UnifiedCodeService,
)
from captive_portal.utils.network_utils import get_client_ip

from .mac_address import extract_mac_address


@dataclass(slots=True)
class GuestOmadaParams:
    """Omada metadata and redirect values submitted with guest requests.

    Attributes:
        client_mac: MAC value from ``clientMac`` query or ``client_mac`` form data.
        client_ip: Omada client IP value used only by GET form rendering.
        site: Omada site identifier supplied by the controller.
        gateway_mac: Gateway MAC metadata.
        ap_mac: Access point MAC metadata.
        radio_id: Radio identifier metadata.
        ssid_name: SSID name metadata.
        vid: VLAN identifier metadata.
        t: Omada timestamp pass-through used by the GET form.
        redirect_url: Omada original redirect URL.
        continue_url: Success redirect candidate from ``continue`` or form data.
    """

    client_mac: str | None = None
    client_ip: str | None = None
    site: str | None = None
    gateway_mac: str | None = None
    ap_mac: str | None = None
    radio_id: str | None = None
    ssid_name: str | None = None
    vid: str | None = None
    t: str | None = None
    redirect_url: str | None = None
    continue_url: str | None = None

    def template_params(self) -> dict[str, str]:
        """Return Omada template fields with current empty-string defaults.

        Returns:
            Mapping keyed by existing template field names.
        """
        return {
            "clientMac": self.client_mac or "",
            "clientIp": self.client_ip or "",
            "site": self.site or "",
            "apMac": self.ap_mac or "",
            "gatewayMac": self.gateway_mac or "",
            "radioId": self.radio_id or "",
            "ssidName": self.ssid_name or "",
            "vid": self.vid or "",
            "t": self.t or "",
            "redirectUrl": self.redirect_url or "",
        }

    def retry_params(self) -> dict[str, str]:
        """Return only non-empty values preserved in authorization retry URLs.

        Returns:
            Mapping using the current retry query keys.
        """
        return {
            key: value
            for key, value in {
                "clientMac": self.client_mac,
                "site": self.site,
                "gatewayMac": self.gateway_mac,
                "apMac": self.ap_mac,
                "vid": self.vid,
                "ssidName": self.ssid_name,
                "radioId": self.radio_id,
                "continue": self.continue_url,
            }.items()
            if value
        }


@dataclass(slots=True)
class GuestAuthorizationDependencies:
    """Resolved dependencies used by the shared authorization flow.

    Attributes:
        rate_limiter: Rate limiter for guest authorization attempts.
        unified_code_service: Service that detects and validates submitted codes.
        redirect_validator: Open-redirect protection service.
        session: SQLModel session for grants and code lookup.
        audit_service: Audit log writer.
        portal_config: Portal configuration containing trusted proxy settings.
        omada_adapter: Optional configured controller adapter.
    """

    rate_limiter: RateLimiter
    unified_code_service: UnifiedCodeService
    redirect_validator: RedirectValidator
    session: Session
    audit_service: AuditService
    portal_config: PortalConfig
    omada_adapter: OmadaControllerAdapter | None


@dataclass(slots=True)
class GuestAuthorizationContext:
    """Per-request values discovered during guest authorization.

    Attributes:
        client_ip: Trusted-proxy-aware client IP address.
        mac_address: Validated and normalized MAC address.
        validation_result: Voucher or booking code validation result.
        vlan_meta: VLAN audit metadata returned by decision helpers.
        grant: Access grant created or redeemed for the request.
        retry_query: Encoded retry query string stored on request state.
    """

    client_ip: str
    mac_address: str | None = None
    validation_result: CodeValidationResult | None = None
    vlan_meta: dict[str, Any] = field(default_factory=dict)
    grant: AccessGrant | None = None
    retry_query: str = ""


@dataclass(frozen=True, slots=True)
class GuestDecisionContext:
    """Immutable inputs shared by voucher and booking decision helpers.

    Attributes:
        request: Incoming FastAPI request.
        audit_service: Audit log writer.
        client_ip: Resolved trusted-proxy-aware client IP address.
        mac_address: Validated and normalized MAC address.
        vid: Submitted VLAN identifier, if any.
    """

    request: Request
    audit_service: AuditService
    client_ip: str
    mac_address: str
    vid: str | None


@dataclass(slots=True)
class AuthorizationDecisionResult:
    """Result returned by voucher and booking decision helpers.

    Attributes:
        grant: Grant produced by the decision helper.
        code_type: Validated code type.
        target_type: Audit target type used for denials.
        target_id: Audit target identifier used for denials.
        vlan_meta: VLAN audit metadata to include on success.
    """

    grant: AccessGrant
    code_type: CodeType
    target_type: str
    target_id: str
    vlan_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def success_target_type(self) -> str:
        """Return the existing success audit target type.

        Returns:
            ``voucher`` for voucher codes and ``booking`` for booking codes.
        """
        return "voucher" if self.code_type == CodeType.VOUCHER else "booking"

    @property
    def denial_target_id(self) -> str:
        """Return the current denial audit target identifier.

        Returns:
            Normalized submitted code captured by the decision helper.
        """
        return self.target_id


def resolve_client_ip(request: Request, portal_config: PortalConfig) -> str:
    """Resolve the trusted-proxy-aware client IP for authorization.

    Args:
        request: Incoming FastAPI request.
        portal_config: Portal configuration containing trusted networks.

    Returns:
        Client IP address used for rate limiting and audit logging.
    """
    return get_client_ip(
        request,
        trust_proxies=True,
        trusted_networks=portal_config.get_trusted_networks(),
    )


async def enforce_rate_limit(
    *,
    rate_limiter: RateLimiter,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
) -> None:
    """Enforce the guest authorization rate limit and audit denials.

    Args:
        rate_limiter: Rate limiter service.
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.

    Raises:
        HTTPException: When the client is rate limited.
    """
    if rate_limiter.is_allowed(client_ip):
        return

    retry_after = rate_limiter.get_retry_after_seconds(client_ip)
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome="rate_limited",
        meta={
            "client_ip": client_ip,
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "retry_after": retry_after,
        },
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=("Too many authorization attempts. Please try again later."),
        headers={"Retry-After": str(retry_after or 60)},
    )


async def extract_authorization_mac(
    *,
    request: Request,
    form_mac: str | None,
    audit_service: AuditService,
    client_ip: str,
) -> str:
    """Extract a MAC address and audit the current failure path.

    Args:
        request: Incoming FastAPI request.
        form_mac: MAC submitted by form data or GET query alias.
        audit_service: Audit log writer.
        client_ip: Resolved client IP address.

    Returns:
        Normalized MAC address.

    Raises:
        HTTPException: When MAC extraction fails.
    """
    try:
        return extract_mac_address(request, form_mac=form_mac)
    except HTTPException as exc:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="error",
            meta={
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "mac_extraction_failed",
                "detail": str(exc.detail),
            },
        )
        raise


async def validate_guest_code(
    *,
    code: str,
    service: UnifiedCodeService,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
) -> CodeValidationResult:
    """Validate a submitted guest code and audit invalid formats.

    Args:
        code: Submitted authorization code.
        service: Unified code validation service.
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.

    Returns:
        Code validation result.

    Raises:
        HTTPException: When code validation rejects the format.
    """
    try:
        return await service.validate_code(code)
    except ValueError as exc:
        await audit_service.log(
            actor=f"guest@{client_ip}",
            action="guest.authorize",
            outcome="denied",
            meta={
                "client_ip": client_ip,
                "mac": mac_address,
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "error": "invalid_code_format",
                "detail": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def audit_controller_failure(
    *,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
    grant: AccessGrant,
    error_detail: str | None,
) -> None:
    """Write the current audit entry for failed controller authorization.

    Args:
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.
        grant: Grant that failed controller authorization.
        error_detail: Diagnostic-only controller error text.
    """
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome="error",
        target_type="access_grant",
        target_id=str(grant.id),
        meta={
            "client_ip": client_ip,
            "mac": mac_address,
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "error": "controller_authorization_failed",
            "detail": error_detail,
        },
    )


async def audit_success(
    *,
    audit_service: AuditService,
    request: Request,
    client_ip: str,
    mac_address: str,
    decision: AuthorizationDecisionResult,
) -> None:
    """Write the current successful authorization audit entry.

    Args:
        audit_service: Audit log writer.
        request: Incoming FastAPI request.
        client_ip: Resolved client IP address.
        mac_address: Validated MAC address.
        decision: Voucher or booking decision result.
    """
    success_meta: dict[str, Any] = {
        "client_ip": client_ip,
        "mac": mac_address,
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "code_type": decision.code_type.value,
        "grant_start": decision.grant.start_utc.isoformat(),
        "grant_end": decision.grant.end_utc.isoformat(),
    }
    if decision.vlan_meta:
        success_meta.update(decision.vlan_meta)
    await audit_service.log(
        actor=f"guest@{client_ip}",
        action="guest.authorize",
        outcome="success",
        target_type=decision.success_target_type,
        target_id=str(decision.grant.id),
        meta=success_meta,
    )
