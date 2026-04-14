# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""One-time migration of YAML/env settings into the database.

On first startup after upgrade, this service reads existing
YAML / environment variable values via
``AppSettings._load_for_migration()`` and writes them into the
corresponding database models.  The migration is idempotent — it
only writes when the target DB record is at its default state, so
subsequent restarts do not overwrite user changes made through the
web UI.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from captive_portal.config.settings import AppSettings
from captive_portal.models.omada_config import OmadaConfig
from captive_portal.models.portal_config import PortalConfig
from captive_portal.security.credential_encryption import encrypt_credential

logger = logging.getLogger("captive_portal.services.config_migration")


class MigrationResult(BaseModel):
    """Summary of what the migration service changed.

    Attributes:
        omada_migrated: Whether Omada settings were migrated.
        session_fields_migrated: Count of session fields migrated.
        guest_url_migrated: Whether the guest external URL was migrated.
        skipped_reason: Human-readable reason when migration was skipped.
    """

    omada_migrated: bool = False
    session_fields_migrated: int = 0
    guest_url_migrated: bool = False
    skipped_reason: str | None = None


def _omada_configured(legacy: dict[str, Any]) -> bool:
    """Check whether legacy values contain a complete Omada config.

    Args:
        legacy: Dict returned by ``AppSettings._load_for_migration()``.

    Returns:
        True when controller URL, username, and password are all
        non-empty.
    """
    return bool(
        str(legacy.get("omada_controller_url", "")).strip()
        and str(legacy.get("omada_username", "")).strip()
        and str(legacy.get("omada_password", "")).strip()
    )


async def migrate_yaml_to_db(
    settings: AppSettings,
    session: Session,
    key_path: str = "/data/.omada_key",
) -> MigrationResult:
    """Migrate settings from YAML/env into DB models.

    This function is idempotent: it only writes when the target
    database record is still at its default/empty state.

    Args:
        settings: Application settings (used only for options_path).
        session: Active database session.
        key_path: Path to the Fernet encryption key file.

    Returns:
        Summary of migrated settings.
    """
    result = MigrationResult()

    # Read legacy values from YAML / env vars
    legacy = AppSettings._load_for_migration()

    # --- Omada migration ---
    stmt: Any = select(OmadaConfig).where(OmadaConfig.id == 1)
    omada_config: Optional[OmadaConfig] = session.exec(stmt).first()

    if omada_config is None or not omada_config.omada_configured:
        # Only migrate if YAML has Omada settings configured
        if _omada_configured(legacy):
            if omada_config is None:
                omada_config = OmadaConfig(id=1)

            omada_config.controller_url = str(legacy["omada_controller_url"]).strip()
            omada_config.username = str(legacy["omada_username"]).strip()
            omada_config.encrypted_password = encrypt_credential(
                str(legacy["omada_password"]), key_path=key_path
            )
            omada_config.site_name = str(legacy["omada_site_name"]).strip() or "Default"
            omada_config.controller_id = str(legacy["omada_controller_id"]).strip()
            omada_config.verify_ssl = bool(legacy["omada_verify_ssl"])

            session.add(omada_config)
            session.commit()

            result.omada_migrated = True
            logger.info(
                "Migrated Omada settings from YAML: url=%s, user=%s",
                omada_config.controller_url,
                omada_config.username,
            )
    else:
        logger.info("Omada settings already in DB — skipping migration.")

    # --- Session and guest URL migration ---
    portal_stmt: Any = select(PortalConfig).where(PortalConfig.id == 1)
    portal_config: Optional[PortalConfig] = session.exec(portal_stmt).first()

    if portal_config is None:
        portal_config = PortalConfig(id=1)
        session.add(portal_config)
        session.commit()
        session.refresh(portal_config)

    # Migrate session_idle_minutes (only if DB is at default and YAML differs)
    idle = int(legacy["session_idle_minutes"])
    if portal_config.session_idle_minutes == 30 and idle != 30:
        portal_config.session_idle_minutes = idle
        result.session_fields_migrated += 1
        logger.info(
            "Migrated session_idle_minutes from YAML: %d",
            idle,
        )

    # Migrate session_max_hours
    max_h = int(legacy["session_max_hours"])
    if portal_config.session_max_hours == 8 and max_h != 8:
        portal_config.session_max_hours = max_h
        result.session_fields_migrated += 1
        logger.info(
            "Migrated session_max_hours from YAML: %d",
            max_h,
        )

    # Migrate guest_external_url
    guest_url = str(legacy["guest_external_url"])
    if portal_config.guest_external_url == "" and guest_url != "":
        portal_config.guest_external_url = guest_url
        result.guest_url_migrated = True
        logger.info(
            "Migrated guest_external_url from YAML: %s",
            guest_url,
        )

    if result.session_fields_migrated > 0 or result.guest_url_migrated:
        session.add(portal_config)
        session.commit()

    return result
