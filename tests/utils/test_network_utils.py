# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for network utility functions."""

import pytest
from unittest.mock import Mock

from fastapi import Request

from captive_portal.utils.network_utils import get_client_ip, validate_mac_address


class TestGetClientIP:
    """Test client IP extraction with various proxy scenarios."""

    def test_direct_connection_no_proxy(self) -> None:
        """Test IP extraction from direct connection without proxy."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}

        ip = get_client_ip(request, trust_proxies=False)
        assert ip == "192.168.1.100"

    def test_no_client_object(self) -> None:
        """Test handling when request.client is None."""
        request = Mock(spec=Request)
        request.client = None
        request.headers = {}

        ip = get_client_ip(request, trust_proxies=False)
        assert ip == "unknown"

    def test_proxy_headers_not_trusted_by_default(self) -> None:
        """Test that proxy headers are ignored when trust_proxies=False."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "203.0.113.50"}

        ip = get_client_ip(request, trust_proxies=False)
        assert ip == "10.0.0.1"  # Should use direct IP, not header

    def test_xff_header_trusted_proxy(self) -> None:
        """Test X-Forwarded-For header from trusted proxy network."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"  # Proxy in trusted network
        request.headers = {"X-Forwarded-For": "203.0.113.50"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "203.0.113.50"

    def test_xff_header_untrusted_proxy(self) -> None:
        """Test X-Forwarded-For ignored from untrusted proxy."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "198.51.100.1"  # Not in trusted networks
        request.headers = {"X-Forwarded-For": "203.0.113.50"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8", "172.16.0.0/12"],
        )
        assert ip == "198.51.100.1"  # Should use direct IP

    def test_xff_multiple_proxies(self) -> None:
        """Test X-Forwarded-For with multiple proxy hops."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"
        # Format: client, proxy1, proxy2
        request.headers = {"X-Forwarded-For": "203.0.113.50, 198.51.100.1, 10.0.0.2"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "203.0.113.50"  # Leftmost IP is original client

    def test_xff_invalid_ip(self) -> None:
        """Test handling of invalid IP in X-Forwarded-For."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "not-an-ip"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "10.0.0.1"  # Falls back to direct IP

    def test_x_real_ip_header(self) -> None:
        """Test X-Real-IP header as fallback."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Real-IP": "203.0.113.50"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "203.0.113.50"

    def test_xff_preferred_over_x_real_ip(self) -> None:
        """Test that X-Forwarded-For is preferred over X-Real-IP."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {
            "X-Forwarded-For": "203.0.113.50",
            "X-Real-IP": "198.51.100.1",
        }

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "203.0.113.50"  # XFF takes precedence

    def test_trust_proxies_without_networks(self) -> None:
        """Test trust_proxies=True without trusted_networks accepts all proxies."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "198.51.100.1"  # Any IP
        request.headers = {"X-Forwarded-For": "203.0.113.50"}

        ip = get_client_ip(request, trust_proxies=True)
        assert ip == "203.0.113.50"

    def test_invalid_direct_ip_address(self) -> None:
        """Test handling of malformed direct IP address."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "invalid-ip"
        request.headers = {"X-Forwarded-For": "203.0.113.50"}

        # Should still return the direct "IP" even if malformed
        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["10.0.0.0/8"],
        )
        assert ip == "invalid-ip"  # Falls back when can't validate

    def test_ipv6_addresses(self) -> None:
        """Test handling of IPv6 addresses."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "::1"  # IPv6 loopback
        request.headers = {"X-Forwarded-For": "2001:db8::1"}

        ip = get_client_ip(
            request,
            trust_proxies=True,
            trusted_networks=["::1/128"],
        )
        assert ip == "2001:db8::1"

    def test_private_network_ranges(self) -> None:
        """Test all common private network ranges."""
        test_cases = [
            ("10.0.0.1", "10.0.0.0/8"),  # Class A private
            ("172.16.0.1", "172.16.0.0/12"),  # Class B private
            ("192.168.1.1", "192.168.0.0/16"),  # Class C private
            ("172.31.255.255", "172.16.0.0/12"),  # End of Class B range
        ]

        for proxy_ip, network in test_cases:
            request = Mock(spec=Request)
            request.client = Mock()
            request.client.host = proxy_ip
            request.headers = {"X-Forwarded-For": "203.0.113.50"}

            ip = get_client_ip(
                request,
                trust_proxies=True,
                trusted_networks=[network],
            )
            assert ip == "203.0.113.50", f"Failed for {proxy_ip} in {network}"


class TestValidateMacAddress:
    """Test MAC address validation and normalization."""

    def test_colon_separated_lowercase(self) -> None:
        """Test validation of lowercase colon-separated MAC."""
        mac = validate_mac_address("aa:bb:cc:dd:ee:ff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_colon_separated_uppercase(self) -> None:
        """Test validation of uppercase colon-separated MAC."""
        mac = validate_mac_address("AA:BB:CC:DD:EE:FF")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_colon_separated_mixed_case(self) -> None:
        """Test validation of mixed-case colon-separated MAC."""
        mac = validate_mac_address("Aa:Bb:Cc:Dd:Ee:Ff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_hyphen_separated(self) -> None:
        """Test validation of hyphen-separated MAC."""
        mac = validate_mac_address("aa-bb-cc-dd-ee-ff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_hyphen_separated_uppercase(self) -> None:
        """Test validation of uppercase hyphen-separated MAC."""
        mac = validate_mac_address("AA-BB-CC-DD-EE-FF")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_dot_separated_cisco(self) -> None:
        """Test validation of Cisco-style dot-separated MAC."""
        mac = validate_mac_address("aabb.ccdd.eeff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_dot_separated_cisco_uppercase(self) -> None:
        """Test validation of uppercase Cisco-style MAC."""
        mac = validate_mac_address("AABB.CCDD.EEFF")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_no_separators(self) -> None:
        """Test validation of unseparated MAC."""
        mac = validate_mac_address("aabbccddeeff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_no_separators_uppercase(self) -> None:
        """Test validation of uppercase unseparated MAC."""
        mac = validate_mac_address("AABBCCDDEEFF")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_all_zeros(self) -> None:
        """Test validation of all-zeros MAC."""
        mac = validate_mac_address("00:00:00:00:00:00")
        assert mac == "00:00:00:00:00:00"

    def test_all_ones(self) -> None:
        """Test validation of broadcast MAC."""
        mac = validate_mac_address("ff:ff:ff:ff:ff:ff")
        assert mac == "FF:FF:FF:FF:FF:FF"

    def test_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_mac_address("")

    def test_too_short(self) -> None:
        """Test that MAC with too few octets raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            validate_mac_address("aa:bb:cc:dd:ee")

    def test_too_long(self) -> None:
        """Test that MAC with too many octets raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            validate_mac_address("aa:bb:cc:dd:ee:ff:00")

    def test_invalid_characters(self) -> None:
        """Test that MAC with invalid characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            validate_mac_address("zz:bb:cc:dd:ee:ff")

    def test_invalid_format_mixed_separators(self) -> None:
        """Test that MAC with mixed separators is handled correctly."""
        # This should work as we strip all separators
        mac = validate_mac_address("aa:bb-cc.dd:ee-ff")
        assert mac == "AA:BB:CC:DD:EE:FF"

    def test_partial_octets(self) -> None:
        """Test that MAC with partial octets raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            validate_mac_address("a:b:c:d:e:f")

    def test_spaces_in_mac(self) -> None:
        """Test that MAC with spaces raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            validate_mac_address("aa bb cc dd ee ff")

    def test_real_world_examples(self) -> None:
        """Test real-world MAC address examples."""
        examples = [
            ("00:1a:2b:3c:4d:5e", "00:1A:2B:3C:4D:5E"),
            ("08-00-27-12-34-56", "08:00:27:12:34:56"),
            ("001a.2b3c.4d5e", "00:1A:2B:3C:4D:5E"),
            ("001a2b3c4d5e", "00:1A:2B:3C:4D:5E"),
        ]

        for input_mac, expected in examples:
            result = validate_mac_address(input_mac)
            assert result == expected, f"Failed for {input_mac}"
