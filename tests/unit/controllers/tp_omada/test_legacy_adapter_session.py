# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for managed legacy adapter client sessions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.controllers.tp_omada.legacy_client import OmadaLegacyClient


class ClosingClientDouble(OmadaLegacyClient):
    """Legacy client double that fails if reused after close."""

    def __init__(self) -> None:
        """Initialize the double."""
        super().__init__(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            username="operator",
            password="secret",
        )
        self.enter_count = 0
        self.post_count = 0

    async def __aenter__(self) -> ClosingClientDouble:
        """Open a managed client session."""
        self.enter_count += 1
        await super().__aenter__()
        return self

    async def _authenticate(self) -> None:
        """Skip network authentication for the double."""

    async def post_with_retry(
        self,
        _endpoint: str,
        _payload: dict[str, object],
        max_retries: int = 4,
        backoff_ms: list[int] | None = None,
    ) -> dict[str, object]:
        """Return a successful legacy response when the session is open."""
        self.post_count += 1
        if self._client is None or self._client.is_closed:
            raise RuntimeError("closed client reused")
        return {"errorCode": 0, "result": {"authorized": True}}


@pytest.mark.asyncio
async def test_managed_legacy_adapter_reopens_between_calls() -> None:
    """Repeated adapter operations reopen managed legacy client sessions."""
    client = ClosingClientDouble()
    adapter = OmadaLegacyAdapter(client=client, site_id="Default")

    await adapter.authorize("AA:BB:CC:DD:EE:FF", datetime.now(timezone.utc))
    await adapter.revoke("AA:BB:CC:DD:EE:FF")

    assert client.enter_count == 2
    assert client.post_count == 2
