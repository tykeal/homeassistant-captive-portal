# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Timer-driven grant expiry deauthorization worker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.controllers.tp_omada.base_client import (
    OmadaClientError,
    OmadaRetryExhaustedError,
)
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus


@dataclass(frozen=True)
class _DueGrant:
    """Controller revocation fields for an expired grant."""

    id: UUID
    mac: str
    controller_grant_id: str | None
    omada_gateway_mac: str | None
    omada_ap_mac: str | None
    omada_vid: str | None
    omada_ssid_name: str | None
    omada_radio_id: str | None


class GrantExpiryService:
    """Periodic worker that expires grants and deauthorizes controller clients."""

    def __init__(
        self,
        *,
        engine: Engine,
        omada_config: OmadaRuntimeConfig | None,
        interval_seconds: float = 5.0,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the expiry worker.

        Args:
            engine: SQLAlchemy engine for worker sessions.
            omada_config: Selected Omada runtime config, if configured.
            interval_seconds: Poll interval.
            logger: Optional logger.
        """
        self.engine = engine
        self.omada_config = omada_config
        self.interval_seconds = interval_seconds
        self.logger = logger or logging.getLogger("captive_portal.grant_expiry")
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        """Run the expiry loop until stopped."""
        while not self._stopped.is_set():
            try:
                await self.process_once()
            except Exception:
                self.logger.exception("Grant expiry worker iteration failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

    async def stop(self) -> None:
        """Request worker shutdown."""
        self._stopped.set()

    async def process_once(self) -> int:
        """Process due active grants once.

        Returns:
            Number of grants marked expired.
        """
        due_grants = self._load_due_grants()
        if not due_grants:
            return 0
        expired_ids: list[UUID] = []
        adapter = self._build_adapter()
        for grant in due_grants:
            if await self._revoke_due_grant(grant, adapter):
                expired_ids.append(grant.id)
        return self._mark_grants_expired(expired_ids)

    def _load_due_grants(self) -> list[_DueGrant]:
        """Load due active grant revocation fields in a short DB session."""
        with Session(self.engine) as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            statement: Any = (
                select(AccessGrant)
                .where(AccessGrant.status == GrantStatus.ACTIVE)
                .where(col(AccessGrant.end_utc) <= now)
            )
            grants = list(session.exec(statement).all())
            return [
                _DueGrant(
                    id=grant.id,
                    mac=grant.mac,
                    controller_grant_id=grant.controller_grant_id,
                    omada_gateway_mac=grant.omada_gateway_mac,
                    omada_ap_mac=grant.omada_ap_mac,
                    omada_vid=grant.omada_vid,
                    omada_ssid_name=grant.omada_ssid_name,
                    omada_radio_id=grant.omada_radio_id,
                )
                for grant in grants
            ]

    def _mark_grants_expired(self, grant_ids: list[UUID]) -> int:
        """Mark successfully revoked grants expired in a short DB session."""
        if not grant_ids:
            return 0
        expired_count = 0
        with Session(self.engine) as session:
            for grant_id in grant_ids:
                grant = session.get(AccessGrant, grant_id)
                if grant is None or grant.status != GrantStatus.ACTIVE:
                    continue
                grant.status = GrantStatus.EXPIRED
                grant.updated_utc = datetime.now(timezone.utc)
                session.add(grant)
                expired_count += 1
            if expired_count:
                session.commit()
        return expired_count

    def _build_adapter(self) -> OmadaControllerAdapter | None:
        """Build a worker-local adapter from runtime config.

        Returns:
            Selected Omada adapter, or ``None`` when not configured.
        """
        if self.omada_config is None:
            return None
        fake_request = cast(Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())))
        fake_request.app.state.omada_config = self.omada_config
        return get_omada_adapter(fake_request)

    async def _revoke_due_grant(
        self,
        grant: _DueGrant,
        adapter: OmadaControllerAdapter | None,
    ) -> bool:
        """Attempt controller revocation for one due grant.

        Args:
            grant: Due active grant.
            adapter: Selected controller adapter, if any.

        Returns:
            True when the grant was marked expired.
        """
        if adapter is not None and grant.mac:
            try:
                await adapter.revoke(
                    mac=grant.mac,
                    grant_id=grant.controller_grant_id,
                    gateway_mac=grant.omada_gateway_mac,
                    ap_mac=grant.omada_ap_mac,
                    vid=grant.omada_vid,
                    ssid_name=grant.omada_ssid_name,
                    radio_id=grant.omada_radio_id,
                )
            except (OmadaClientError, OmadaRetryExhaustedError) as exc:
                self.logger.error("Controller expiry revoke failed for MAC %s: %s", grant.mac, exc)
                return False
        return True
