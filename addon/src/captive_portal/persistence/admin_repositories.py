# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Administrative repository implementations."""

from typing import Any, Optional, cast
from uuid import UUID

from sqlmodel import select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.persistence.repository_base import BaseRepository


class AdminUserRepository(BaseRepository[AdminUser]):
    """Repository for AdminUser entities."""

    def get_model_class(self) -> type[AdminUser]:
        """Return AdminUser model class."""
        return AdminUser

    def get_by_id(self, user_id: UUID) -> Optional[AdminUser]:
        """Retrieve admin user by ID.

        Args:
            user_id: User UUID.

        Returns:
            AdminUser instance or None.
        """
        return cast(Optional[AdminUser], self.session.get(AdminUser, user_id))

    def get_by_username(self, username: str) -> Optional[AdminUser]:
        """Retrieve admin user by username.

        Args:
            username: Username (case-sensitive).

        Returns:
            AdminUser instance or None.
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
            log_id: Log entry UUID.

        Returns:
            AuditLog instance or None.
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
            config_id: Config UUID.

        Returns:
            HAIntegrationConfig instance or None.
        """
        return cast(Optional[HAIntegrationConfig], self.session.get(HAIntegrationConfig, config_id))

    def get_by_integration_id(self, integration_id: str) -> Optional[HAIntegrationConfig]:
        """Retrieve config by integration ID.

        Args:
            integration_id: HA integration identifier.

        Returns:
            HAIntegrationConfig instance or None.
        """
        statement: Any = select(HAIntegrationConfig).where(
            HAIntegrationConfig.integration_id == integration_id
        )
        result: HAIntegrationConfig | None = self.session.exec(statement).first()
        return result
