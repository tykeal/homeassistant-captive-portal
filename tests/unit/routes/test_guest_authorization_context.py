# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization context grouping helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.services.unified_code_service import CodeType


def test_omada_params_preserve_retry_keys_only() -> None:
    """Omada grouping preserves current retry-query key behavior."""
    from captive_portal.api.routes.guest_authorization.context import GuestOmadaParams

    params = GuestOmadaParams(
        client_mac="AA-BB-CC-DD-EE-FF",
        client_ip="192.0.2.25",
        site="686982d482171c5562624ad1",
        gateway_mac="11-22-33-44-55-66",
        ap_mac="22-33-44-55-66-77",
        radio_id="1",
        ssid_name="Guest",
        vid="100",
        t="123",
        redirect_url="https://example.test",
        continue_url="/guest/welcome",
    )

    assert params.template_params() == {
        "clientMac": "AA-BB-CC-DD-EE-FF",
        "clientIp": "192.0.2.25",
        "site": "686982d482171c5562624ad1",
        "apMac": "22-33-44-55-66-77",
        "gatewayMac": "11-22-33-44-55-66",
        "radioId": "1",
        "ssidName": "Guest",
        "vid": "100",
        "t": "123",
        "redirectUrl": "https://example.test",
    }
    assert params.retry_params() == {
        "clientMac": "AA-BB-CC-DD-EE-FF",
        "site": "686982d482171c5562624ad1",
        "gatewayMac": "11-22-33-44-55-66",
        "apMac": "22-33-44-55-66-77",
        "vid": "100",
        "ssidName": "Guest",
        "radioId": "1",
        "continue": "/guest/welcome",
    }


def test_decision_result_preserves_audit_target() -> None:
    """Decision results expose the current grant and audit target metadata."""
    from captive_portal.api.routes.guest_authorization.context import AuthorizationDecisionResult

    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime.now(timezone.utc),
        status=GrantStatus.PENDING,
    )
    result = AuthorizationDecisionResult(
        grant=grant,
        code_type=CodeType.VOUCHER,
        target_type="voucher",
        target_id="ABCD1234",
        vlan_meta={"vlan_allowed": True},
    )

    assert result.grant is grant
    assert result.success_target_type == "voucher"
    assert result.denial_target_id == "ABCD1234"
