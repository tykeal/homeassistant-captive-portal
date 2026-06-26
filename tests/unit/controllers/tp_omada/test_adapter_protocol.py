# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Omada controller adapter Protocol contract."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

import pytest

from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter


class _FakeAdapter:
    """Fake adapter that intentionally implements the shared contract."""

    async def authorize(
        self,
        mac: str,
        expires_at: datetime,
        upload_limit_kbps: int = 0,
        download_limit_kbps: int = 0,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
        vid: str | None = None,
    ) -> dict[str, Any]:
        """Authorize the fake client and echo contract parameters."""
        return {"grant_id": mac, "status": "active", "mac": mac}

    async def revoke(
        self,
        mac: str,
        grant_id: str | None = None,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        vid: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
    ) -> dict[str, Any]:
        """Revoke the fake client and echo contract parameters."""
        return {"success": True, "mac": mac}

    async def update(
        self,
        mac: str,
        expires_at: datetime,
        grant_id: str | None = None,
    ) -> dict[str, Any]:
        """Update the fake client and echo contract parameters."""
        return {"grant_id": grant_id or mac, "status": "active", "mac": mac}

    async def get_status(self, mac: str) -> dict[str, Any]:
        """Return fake best-effort status."""
        return {"mac": mac, "authorized": True, "remaining_seconds": 0}


def test_protocol_exposes_async_contract_methods() -> None:
    """Protocol exposes the required async controller operations."""
    for name in ("authorize", "revoke", "update", "get_status"):
        method = getattr(OmadaControllerAdapter, name)
        assert inspect.iscoroutinefunction(method)


def test_protocol_authorize_accepts_legacy_context_parameters() -> None:
    """Authorize signature accepts legacy Gateway/EAP context parameters."""
    sig = inspect.signature(OmadaControllerAdapter.authorize)
    assert list(sig.parameters) == [
        "self",
        "mac",
        "expires_at",
        "upload_limit_kbps",
        "download_limit_kbps",
        "gateway_mac",
        "ap_mac",
        "ssid_name",
        "radio_id",
        "vid",
    ]


@pytest.mark.asyncio
async def test_fake_adapter_satisfies_runtime_protocol() -> None:
    """A structurally compatible implementation satisfies the Protocol."""
    adapter: OmadaControllerAdapter = _FakeAdapter()
    result = await adapter.authorize(
        "AA:BB:CC:DD:EE:FF",
        datetime.now(timezone.utc),
        gateway_mac="00:11:22:33:44:55",
        vid="10",
    )
    assert result["status"] == "active"
