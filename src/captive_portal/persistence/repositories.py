# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Repository abstraction layer for data access."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar, List, cast, Any
from uuid import UUID

from sqlmodel import Session, select


from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Base repository with common CRUD operations.

    Type parameter T represents the model class.
    """

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLModel/SQLAlchemy session
        """
        self.session = session

    @abstractmethod
    def get_model_class(self) -> type[T]:
        """Return the model class this repository manages."""
        ...

    def add(self, entity: T) -> T:
        """Add new entity to session and flush.

        Args:
            entity: Model instance to add

        Returns:
            Added entity with generated fields populated
        """
        self.session.add(entity)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def commit(self) -> None:
        """Commit current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        self.session.rollback()


class VoucherRepository(BaseRepository[Voucher]):
    """Repository for Voucher entities."""

    def get_model_class(self) -> type[Voucher]:
        """Return Voucher model class."""
        return Voucher

    def get_by_code(self, code: str) -> Optional[Voucher]:
        """Retrieve voucher by code (PK).

        Args:
            code: Voucher code

        Returns:
            Voucher instance or None
        """
        return cast(Optional[Voucher], self.session.get(Voucher, code))

    def find_by_booking_ref(self, booking_ref: str) -> List[Voucher]:
        """Find vouchers by booking reference (case-sensitive).

        Args:
            booking_ref: Booking reference

        Returns:
            List of matching vouchers
        """
        statement: Any = select(Voucher).where(Voucher.booking_ref == booking_ref)
        results: list[Voucher] = list(self.session.exec(statement).all())
        return results


class AccessGrantRepository(BaseRepository[AccessGrant]):
    """Repository for AccessGrant entities."""

    def get_model_class(self) -> type[AccessGrant]:
        """Return AccessGrant model class."""
        return AccessGrant

    def get_by_id(self, grant_id: UUID) -> Optional[AccessGrant]:
        """Retrieve grant by ID.

        Args:
            grant_id: Grant UUID

        Returns:
            AccessGrant instance or None
        """
        return cast(Optional[AccessGrant], self.session.get(AccessGrant, grant_id))

    def find_active_by_mac(self, mac: str) -> List[AccessGrant]:
        """Find active grants for MAC address.

        Args:
            mac: Device MAC address

        Returns:
            List of active grants
        """
        from captive_portal.models.access_grant import GrantStatus

        statement: Any = (
            select(AccessGrant)
            .where(AccessGrant.mac == mac)
            .where(AccessGrant.status == GrantStatus.ACTIVE)
        )
        results: list[AccessGrant] = list(self.session.exec(statement).all())
        return results


class AdminUserRepository(BaseRepository[AdminUser]):
    """Repository for AdminUser entities."""

    def get_model_class(self) -> type[AdminUser]:
        """Return AdminUser model class."""
        return AdminUser

    def get_by_id(self, user_id: UUID) -> Optional[AdminUser]:
        """Retrieve admin user by ID.

        Args:
            user_id: User UUID

        Returns:
            AdminUser instance or None
        """
        return cast(Optional[AdminUser], self.session.get(AdminUser, user_id))

    def get_by_username(self, username: str) -> Optional[AdminUser]:
        """Retrieve admin user by username.

        Args:
            username: Username (case-sensitive)

        Returns:
            AdminUser instance or None
        """
        statement: Any = select(AdminUser).where(AdminUser.username == username)
        result: AdminUser | None = self.session.exec(statement).first()
        return result


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog entities (append-only)."""

    def get_model_class(self) -> type[AuditLog]:
        """Return AuditLog model class."""
        return AuditLog

    def get_by_id(self, log_id: UUID) -> Optional[AuditLog]:
        """Retrieve audit log by ID.

        Args:
            log_id: Log entry UUID

        Returns:
            AuditLog instance or None
        """
        return cast(Optional[AuditLog], self.session.get(AuditLog, log_id))


class HAIntegrationConfigRepository(BaseRepository[HAIntegrationConfig]):
    """Repository for HAIntegrationConfig entities."""

    def get_model_class(self) -> type[HAIntegrationConfig]:
        """Return HAIntegrationConfig model class."""
        return HAIntegrationConfig

    def get_by_id(self, config_id: UUID) -> Optional[HAIntegrationConfig]:
        """Retrieve config by ID.

        Args:
            config_id: Config UUID

        Returns:
            HAIntegrationConfig instance or None
        """
        return cast(Optional[HAIntegrationConfig], self.session.get(HAIntegrationConfig, config_id))

    def get_by_integration_id(self, integration_id: str) -> Optional[HAIntegrationConfig]:
        """Retrieve config by integration ID.

        Args:
            integration_id: HA integration identifier

        Returns:
            HAIntegrationConfig instance or None
        """
        statement: Any = select(HAIntegrationConfig).where(
            HAIntegrationConfig.integration_id == integration_id
        )
        result: HAIntegrationConfig | None = self.session.exec(statement).first()
        return result


class RentalControlEventRepository(BaseRepository[RentalControlEvent]):
    """Repository for RentalControlEvent entities."""

    def get_model_class(self) -> type[RentalControlEvent]:
        """Return RentalControlEvent model class."""
        return RentalControlEvent

    def get_by_id(self, event_id: int) -> Optional[RentalControlEvent]:
        """Retrieve event by ID.

        Args:
            event_id: Event ID

        Returns:
            RentalControlEvent instance or None
        """
        return cast(Optional[RentalControlEvent], self.session.get(RentalControlEvent, event_id))

    async def upsert(self, event: RentalControlEvent) -> RentalControlEvent:
        """Insert or update event record.

        Updates existing event based on (integration_id, event_index) unique constraint.

        Args:
            event: Event to insert/update

        Returns:
            Updated event instance
        """
        # Check for existing event
        statement: Any = select(RentalControlEvent).where(
            RentalControlEvent.integration_id == event.integration_id,
            RentalControlEvent.event_index == event.event_index,
        )
        existing: RentalControlEvent | None = self.session.exec(statement).first()

        if existing:
            # Update existing
            existing.slot_name = event.slot_name
            existing.slot_code = event.slot_code
            existing.last_four = event.last_four
            existing.start_utc = event.start_utc
            existing.end_utc = event.end_utc
            existing.raw_attributes = event.raw_attributes
            existing.updated_utc = datetime.now(timezone.utc)
            self.session.add(existing)
            self.session.flush()
            self.session.refresh(existing)
            return existing
        else:
            # Insert new
            return self.add(event)

    async def delete_events_older_than(self, cutoff_date: datetime) -> int:
        """Delete events with end_utc older than cutoff date.

        Args:
            cutoff_date: Cutoff timestamp (UTC)

        Returns:
            Number of deleted events
        """
        statement: Any = select(RentalControlEvent).where(RentalControlEvent.end_utc < cutoff_date)
        events_to_delete: list[RentalControlEvent] = list(self.session.exec(statement).all())

        for event in events_to_delete:
            self.session.delete(event)

        self.session.flush()
        return len(events_to_delete)
