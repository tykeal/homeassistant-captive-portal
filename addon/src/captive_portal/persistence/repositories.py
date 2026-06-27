# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Repository abstraction layer for data access."""

from captive_portal.persistence.access_grant_repository import AccessGrantRepository
from captive_portal.persistence.admin_repositories import (
    AdminUserRepository,
    AuditLogRepository,
    HAIntegrationConfigRepository,
)
from captive_portal.persistence.rental_control_event_repository import (
    RentalControlEventRepository,
)
from captive_portal.persistence.repository_base import BaseRepository
from captive_portal.persistence.voucher_repository import VoucherRepository

__all__ = [
    "AccessGrantRepository",
    "AdminUserRepository",
    "AuditLogRepository",
    "BaseRepository",
    "HAIntegrationConfigRepository",
    "RentalControlEventRepository",
    "VoucherRepository",
]
