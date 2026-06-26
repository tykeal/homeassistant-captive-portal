# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAPI MAC address formatting."""

from __future__ import annotations

import pytest

from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.openapi_adapter import format_openapi_mac


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF"),
        ("AA:BB:CC:DD:EE:FF", "AA-BB-CC-DD-EE-FF"),
        ("aa-bb-cc-dd-ee-ff", "AA-BB-CC-DD-EE-FF"),
        ("AABBCCDDEEFF", "AA-BB-CC-DD-EE-FF"),
    ],
)
def test_format_openapi_mac(raw: str, expected: str) -> None:
    """Valid MAC formats normalize to uppercase dash form."""
    assert format_openapi_mac(raw) == expected


def test_invalid_mac_raises_before_http_call() -> None:
    """Invalid MAC values are rejected by the adapter boundary."""
    with pytest.raises(OmadaClientError):
        format_openapi_mac("not-a-mac")
