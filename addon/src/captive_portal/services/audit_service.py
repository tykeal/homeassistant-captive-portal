# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Audit logging service for tracking admin and system events."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlmodel import Session

from captive_portal.models.audit_log import AuditLog
from captive_portal.persistence.repositories import AuditLogRepository


class AuditService:
    """Service for creating immutable audit log entries."""

    def __init__(
        self,
        session: Session,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        """Initialize audit service.

        Args:
            session: Database session
            audit_repo: Optional audit repository (creates if None)
        """
        self.session = session
        self.audit_repo = audit_repo or AuditLogRepository(session)

    async def log(
        self,
        actor: str,
        action: str,
        outcome: str,
        role_snapshot: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Create audit log entry.

        Args:
            actor: Username or system identifier performing action
            action: Action identifier (e.g., 'voucher.create', 'grant.revoke')
            outcome: Outcome code (e.g., 'success', 'denied', 'error')
            role_snapshot: Optional role at time of action (for RBAC auditing)
            target_type: Optional target entity type (e.g., 'voucher', 'grant')
            target_id: Optional target entity ID (UUID or code)
            meta: Optional JSON metadata (e.g., reason, IP, error details)

        Returns:
            Created audit log entry (immutable)
        """
        entry = AuditLog(
            actor=actor,
            role_snapshot=role_snapshot,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            meta=meta or {},
        )

        self.audit_repo.add(entry)
        self.audit_repo.commit()
        return entry

    async def log_voucher_created(
        self,
        actor: str,
        role: str,
        voucher_code: str,
        duration_minutes: int,
        booking_ref: Optional[str] = None,
    ) -> AuditLog:
        """Log voucher creation event.

        Args:
            actor: Admin username
            role: Admin role at time of creation
            voucher_code: Generated voucher code
            duration_minutes: Grant duration
            booking_ref: Optional booking reference

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=actor,
            role_snapshot=role,
            action="voucher.create",
            outcome="success",
            target_type="voucher",
            target_id=voucher_code,
            meta={
                "duration_minutes": duration_minutes,
                "booking_ref": booking_ref,
            },
        )

    async def log_voucher_redeemed(
        self,
        voucher_code: str,
        mac: str,
        grant_id: UUID,
        outcome: str = "success",
        error: Optional[str] = None,
    ) -> AuditLog:
        """Log voucher redemption attempt.

        Args:
            voucher_code: Voucher code being redeemed
            mac: Device MAC address
            grant_id: Created grant UUID (if successful)
            outcome: 'success', 'denied', or 'error'
            error: Optional error message (if outcome != success)

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=f"guest:{mac}",
            action="voucher.redeem",
            outcome=outcome,
            target_type="voucher",
            target_id=voucher_code,
            meta={
                "mac": mac,
                "grant_id": str(grant_id) if grant_id else None,
                "error": error,
            },
        )

    async def log_grant_extended(
        self,
        actor: str,
        role: str,
        grant_id: UUID,
        additional_minutes: int,
        new_end_utc: datetime,
    ) -> AuditLog:
        """Log grant extension event.

        Args:
            actor: Admin username
            role: Admin role
            grant_id: Grant UUID
            additional_minutes: Minutes added
            new_end_utc: New end timestamp

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=actor,
            role_snapshot=role,
            action="grant.extend",
            outcome="success",
            target_type="grant",
            target_id=str(grant_id),
            meta={
                "additional_minutes": additional_minutes,
                "new_end_utc": new_end_utc.isoformat(),
            },
        )

    async def log_grant_revoked(
        self,
        actor: str,
        role: str,
        grant_id: UUID,
        reason: Optional[str] = None,
    ) -> AuditLog:
        """Log grant revocation event.

        Args:
            actor: Admin username
            role: Admin role
            grant_id: Grant UUID
            reason: Optional revocation reason

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=actor,
            role_snapshot=role,
            action="grant.revoke",
            outcome="success",
            target_type="grant",
            target_id=str(grant_id),
            meta={"reason": reason},
        )

    async def log_rbac_denied(
        self,
        actor: str,
        role: str,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> AuditLog:
        """Log RBAC permission denied event.

        Args:
            actor: Username attempting action
            role: User role
            action: Action attempted (e.g., 'grants.extend')
            target_type: Optional target entity type
            target_id: Optional target entity ID

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=actor,
            role_snapshot=role,
            action=action,
            outcome="denied",
            target_type=target_type,
            target_id=target_id,
            meta={"rbac_denial": True},
        )

    async def log_admin_action(
        self,
        admin_id: UUID,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Log general admin action.

        Args:
            admin_id: Admin user ID performing action
            action: Action identifier (e.g., 'list_grants', 'extend_grant')
            target_type: Optional target entity type
            target_id: Optional target entity ID
            metadata: Optional additional metadata

        Returns:
            Audit log entry
        """
        return await self.log(
            actor=str(admin_id),
            action=action,
            outcome="success",
            target_type=target_type,
            target_id=target_id,
            meta=metadata,
        )
