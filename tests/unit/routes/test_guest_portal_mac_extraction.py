# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for MAC address extraction and Omada parameter handling.

Validates that _extract_mac_address correctly extracts MAC addresses
from headers, form data, and query parameters, with proper priority
ordering.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from captive_portal.api.routes.guest_portal import _extract_mac_address


class TestExtractMacAddressHeaders:
    """Tests for MAC extraction from HTTP headers (existing behavior)."""

    def test_x_mac_address_header(self) -> None:
        """X-MAC-Address header should be used when present."""
        request = Mock(spec=Request)
        request.headers = {"X-MAC-Address": "AA:BB:CC:DD:EE:FF"}
        request.query_params = {}

        result = _extract_mac_address(request)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_x_client_mac_header(self) -> None:
        """X-Client-Mac header should be used as fallback."""
        request = Mock(spec=Request)
        request.headers = {"X-Client-Mac": "11:22:33:44:55:66"}
        request.query_params = {}

        result = _extract_mac_address(request)
        assert result == "11:22:33:44:55:66"

    def test_client_mac_header(self) -> None:
        """Client-MAC header should be used as fallback."""
        request = Mock(spec=Request)
        request.headers = {"Client-MAC": "AA:BB:CC:DD:EE:FF"}
        request.query_params = {}

        result = _extract_mac_address(request)
        assert result == "AA:BB:CC:DD:EE:FF"


class TestExtractMacAddressFormData:
    """Tests for MAC extraction from form data (clientMac hidden field)."""

    def test_form_mac_used_when_no_header(self) -> None:
        """Form clientMac should be used when no header is present."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {}

        result = _extract_mac_address(request, form_mac="1E-4A-E7-40-5C-D8")
        assert result == "1E:4A:E7:40:5C:D8"

    def test_header_takes_priority_over_form_mac(self) -> None:
        """Header MAC should take priority over form data MAC."""
        request = Mock(spec=Request)
        request.headers = {"X-MAC-Address": "AA:BB:CC:DD:EE:FF"}
        request.query_params = {}

        result = _extract_mac_address(request, form_mac="11:22:33:44:55:66")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_form_mac_empty_string_ignored(self) -> None:
        """Empty form_mac should be ignored."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "AA:BB:CC:DD:EE:FF"}

        result = _extract_mac_address(request, form_mac="")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_form_mac_whitespace_only_ignored(self) -> None:
        """Whitespace-only form_mac should be ignored."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "AA:BB:CC:DD:EE:FF"}

        result = _extract_mac_address(request, form_mac="   ")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_form_mac_none_ignored(self) -> None:
        """None form_mac should fall through to query params."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "AA:BB:CC:DD:EE:FF"}

        result = _extract_mac_address(request, form_mac=None)
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_form_mac_stripped(self) -> None:
        """Form MAC with surrounding whitespace should be stripped."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {}

        result = _extract_mac_address(request, form_mac="  AA:BB:CC:DD:EE:FF  ")
        assert result == "AA:BB:CC:DD:EE:FF"


class TestExtractMacAddressQueryParams:
    """Tests for MAC extraction from query parameters."""

    def test_query_param_clientmac(self) -> None:
        """clientMac query parameter should be used as last resort."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "1E-4A-E7-40-5C-D8"}

        result = _extract_mac_address(request)
        assert result == "1E:4A:E7:40:5C:D8"

    def test_form_mac_takes_priority_over_query_param(self) -> None:
        """Form data MAC should take priority over query param MAC."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "11:22:33:44:55:66"}

        result = _extract_mac_address(request, form_mac="AA:BB:CC:DD:EE:FF")
        assert result == "AA:BB:CC:DD:EE:FF"


class TestExtractMacAddressOmadaFormat:
    """Tests for Omada-style dash-separated MAC addresses."""

    def test_omada_dash_separated_mac(self) -> None:
        """Omada sends MAC as 1E-4A-E7-40-5C-D8; should normalize."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {}

        result = _extract_mac_address(request, form_mac="1E-4A-E7-40-5C-D8")
        assert result == "1E:4A:E7:40:5C:D8"

    def test_omada_mac_from_query_param(self) -> None:
        """Omada MAC from query param should be normalized."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {"clientMac": "EC-75-0C-2A-AC-BE"}

        result = _extract_mac_address(request)
        assert result == "EC:75:0C:2A:AC:BE"


class TestExtractMacAddressErrors:
    """Tests for error cases in MAC extraction."""

    def test_no_mac_anywhere_raises_400(self) -> None:
        """Missing MAC should raise HTTPException 400."""
        request = Mock(spec=Request)
        request.headers = {}
        request.query_params = {}

        with pytest.raises(HTTPException) as exc_info:
            _extract_mac_address(request)

        assert exc_info.value.status_code == 400
        assert "Unable to determine device MAC address" in str(exc_info.value.detail)

    def test_invalid_mac_raises_400(self) -> None:
        """Invalid MAC format should raise HTTPException 400."""
        request = Mock(spec=Request)
        request.headers = {"X-MAC-Address": "not-a-mac"}
        request.query_params = {}

        with pytest.raises(HTTPException) as exc_info:
            _extract_mac_address(request)

        assert exc_info.value.status_code == 400
        assert "Invalid MAC address format" in str(exc_info.value.detail)
