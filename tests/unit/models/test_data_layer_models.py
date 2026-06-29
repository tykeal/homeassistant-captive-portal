# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for data-layer SQLModel validators."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.models.voucher import Voucher


def test_portal_config_trusted_networks_default_when_none() -> None:
    """PortalConfig replaces None trusted networks with private CIDR defaults."""
    config = PortalConfig(trusted_proxy_networks=None)

    assert config.trusted_proxy_networks == '["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]'


def test_portal_config_rejects_non_list_trusted_network_json() -> None:
    """PortalConfig rejects trusted network JSON that is not a list."""
    with pytest.raises(ValidationError, match="trusted_proxy_networks must be a JSON list"):
        PortalConfig(trusted_proxy_networks='{"cidr":"10.0.0.0/8"}')


def test_portal_config_rejects_non_string_trusted_network_entries() -> None:
    """PortalConfig rejects trusted network lists containing non-strings."""
    with pytest.raises(ValidationError, match="All network entries must be strings"):
        PortalConfig(trusted_proxy_networks='["10.0.0.0/8", 123]')


def test_portal_config_rejects_invalid_trusted_network_json() -> None:
    """PortalConfig reports invalid trusted network JSON."""
    with pytest.raises(ValidationError, match="Invalid JSON in trusted_proxy_networks"):
        PortalConfig(trusted_proxy_networks="[")


def test_portal_config_get_trusted_networks_handles_none_assignment() -> None:
    """PortalConfig returns defaults if trusted networks are cleared after creation."""
    config = PortalConfig()
    object.__setattr__(config, "trusted_proxy_networks", None)

    assert config.get_trusted_networks() == ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]


def test_voucher_booking_ref_is_stripped_and_empty_becomes_none() -> None:
    """Voucher booking references are normalized without changing case."""
    assert (
        Voucher.model_validate(
            {"code": "BOOKING1", "duration_minutes": 60, "booking_ref": " AbC123 "}
        ).booking_ref
        == "AbC123"
    )
    assert (
        Voucher.model_validate(
            {"code": "BOOKING2", "duration_minutes": 60, "booking_ref": ""}
        ).booking_ref
        is None
    )


def test_voucher_allowed_vlans_accepts_none_and_sorts_unique_values() -> None:
    """Voucher VLAN validation accepts None and normalizes duplicate VLAN IDs."""
    assert (
        Voucher.model_validate(
            {"code": "VLANOK01", "duration_minutes": 60, "allowed_vlans": None}
        ).allowed_vlans
        is None
    )
    voucher = Voucher.model_validate(
        {"code": "VLANOK02", "duration_minutes": 60, "allowed_vlans": [30, 10, 30]}
    )

    assert voucher.allowed_vlans == [10, 30]


def test_voucher_allowed_vlans_rejects_non_list() -> None:
    """Voucher VLAN validation rejects non-list values."""
    with pytest.raises(ValidationError, match="allowed_vlans must be a list"):
        Voucher.model_validate({"code": "VLANBAD1", "duration_minutes": 60, "allowed_vlans": "10"})


@pytest.mark.parametrize("vlan", [True, 0, 4095, "10"])
def test_voucher_allowed_vlans_rejects_invalid_vlan_ids(vlan: object) -> None:
    """Voucher VLAN validation rejects booleans and out-of-range values."""
    with pytest.raises(ValidationError, match="Invalid VLAN ID"):
        Voucher.model_validate(
            {"code": "VLANBAD2", "duration_minutes": 60, "allowed_vlans": [vlan]}
        )


def test_ha_integration_allowed_vlans_accepts_none_and_sorts_unique_values() -> None:
    """HA integration VLAN validation accepts None and normalizes duplicates."""
    assert (
        HAIntegrationConfig.model_validate({"integration_id": "ha-vlan-none"}).allowed_vlans is None
    )
    config = HAIntegrationConfig.model_validate(
        {"integration_id": "ha-vlan-list", "allowed_vlans": [20, 10, 20]}
    )

    assert config.allowed_vlans == [10, 20]


def test_ha_integration_allowed_vlans_rejects_non_list() -> None:
    """HA integration VLAN validation rejects non-list values."""
    with pytest.raises(ValidationError, match="allowed_vlans must be a list"):
        HAIntegrationConfig.model_validate({"integration_id": "ha-vlan-bad", "allowed_vlans": "10"})


@pytest.mark.parametrize("vlan", [False, 0, 4095, "10"])
def test_ha_integration_allowed_vlans_rejects_invalid_ids(vlan: object) -> None:
    """HA integration VLAN validation rejects booleans and out-of-range values."""
    with pytest.raises(ValidationError, match="Invalid VLAN ID"):
        HAIntegrationConfig.model_validate(
            {"integration_id": "ha-vlan-invalid", "allowed_vlans": [vlan]}
        )


def test_omada_config_legacy_alias_and_missing_client_id() -> None:
    """OmadaConfig exposes legacy aliases and reports missing OpenAPI client IDs."""
    legacy = OmadaConfig(
        controller_url="https://omada.example.test",
        username="operator",
        encrypted_password="cipher",
    )
    partial = OmadaConfig(
        controller_url="https://omada.example.test",
        encrypted_client_secret="secret",
    )

    assert legacy.legacy_credentials_present is True
    assert partial.missing_openapi_fields == ("client_id",)
