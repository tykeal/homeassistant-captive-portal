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
from captive_portal.security.credential_encryption import decrypt_credential, encrypt_credential

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


def _openapi_values_present(legacy: dict[str, Any]) -> bool:
    """Check whether migration input contains OpenAPI settings.

    Args:
        legacy: Dict returned by ``AppSettings._load_for_migration()``.

    Returns:
        True when OpenAPI client fields or a non-default mode are present.
    """
    return bool(
        str(legacy.get("omada_client_id", "")).strip()
        or str(legacy.get("omada_client_secret", "")).strip()
        or str(legacy.get("omada_openapi_mode", "auto")).strip().lower() != "auto"
    )


def _apply_openapi_fields(
    omada_config: OmadaConfig,
    legacy: dict[str, Any],
    key_path: str,
) -> bool:
    """Apply OpenAPI migration values to an Omada config.

    Args:
        omada_config: Mutable Omada configuration model.
        legacy: Migration value dictionary.
        key_path: Fernet key path for client secret encryption.

    Returns:
        True when any OpenAPI field changed.
    """
    changed = False
    client_id = str(legacy.get("omada_client_id", "")).strip()
    if client_id and omada_config.client_id != client_id:
        omada_config.client_id = client_id
        changed = True

    client_secret = str(legacy.get("omada_client_secret", "")).strip()
    if client_secret and not _secret_matches_existing(
        omada_config.encrypted_client_secret,
        client_secret,
        key_path,
    ):
        omada_config.encrypted_client_secret = encrypt_credential(
            client_secret,
            key_path=key_path,
        )
        changed = True

    mode = str(legacy.get("omada_openapi_mode", "auto")).strip().lower() or "auto"
    if omada_config.openapi_mode != mode:
        omada_config.openapi_mode = mode
        changed = True

    return changed


def _secret_matches_existing(ciphertext: str, plaintext: str, key_path: str) -> bool:
    """Return whether existing ciphertext decrypts to plaintext.

    Args:
        ciphertext: Existing encrypted secret.
        plaintext: Candidate plaintext secret from migration input.
        key_path: Fernet key path.

    Returns:
        True when ciphertext decrypts to the same plaintext.
    """
    if not ciphertext:
        return False
    try:
        return decrypt_credential(ciphertext, key_path=key_path) == plaintext
    except Exception:
        return False


def _apply_shared_omada_fields(omada_config: OmadaConfig, legacy: dict[str, Any]) -> bool:
    """Apply controller fields shared by legacy and OpenAPI backends.

    Args:
        omada_config: Mutable Omada configuration model.
        legacy: Migration value dictionary.

    Returns:
        True when any shared field changed.
    """
    changed = False
    shared_values: dict[str, Any] = {
        "controller_url": str(legacy["omada_controller_url"]).strip(),
        "site_name": str(legacy["omada_site_name"]).strip() or "Default",
        "controller_id": str(legacy["omada_controller_id"]).strip(),
        "verify_ssl": bool(legacy["omada_verify_ssl"]),
    }
    for field_name, value in shared_values.items():
        if getattr(omada_config, field_name) != value:
            setattr(omada_config, field_name, value)
            changed = True
    return changed


def _openapi_fields_default(omada_config: OmadaConfig) -> bool:
    """Return whether OpenAPI DB fields are still migration defaults.

    Args:
        omada_config: Existing Omada configuration record.

    Returns:
        True when no OpenAPI client ID, secret, or explicit mode is stored.
    """
    return (
        not omada_config.client_id.strip()
        and not omada_config.encrypted_client_secret.strip()
        and omada_config.openapi_mode == "auto"
    )


def _apply_legacy_omada_fields(
    omada_config: OmadaConfig,
    legacy: dict[str, Any],
    key_path: str,
) -> None:
    """Apply legacy Omada settings from migration input.

    Args:
        omada_config: Mutable Omada configuration model.
        legacy: Migration value dictionary.
        key_path: Fernet key path for legacy password encryption.
    """
    _apply_shared_omada_fields(omada_config, legacy)
    omada_config.username = str(legacy["omada_username"]).strip()
    omada_config.encrypted_password = encrypt_credential(
        str(legacy["omada_password"]),
        key_path=key_path,
    )


def _migrate_omada_settings(
    legacy: dict[str, Any],
    session: Session,
    key_path: str,
) -> bool:
    """Migrate Omada settings from legacy sources into the database.

    Args:
        legacy: Migration value dictionary.
        session: Active database session.
        key_path: Fernet key path for credential encryption.

    Returns:
        True when Omada settings were changed.
    """
    stmt: Any = select(OmadaConfig).where(OmadaConfig.id == 1)
    omada_config: Optional[OmadaConfig] = session.exec(stmt).first()

    can_write_base = omada_config is None or not (
        omada_config.omada_configured or omada_config.openapi_configured
    )
    if omada_config is None:
        omada_config = OmadaConfig(id=1)

    changed = False
    if can_write_base and (_omada_configured(legacy) or _openapi_values_present(legacy)):
        changed = _apply_shared_omada_fields(omada_config, legacy) or changed

    if can_write_base and _omada_configured(legacy):
        _apply_legacy_omada_fields(omada_config, legacy, key_path)
        changed = True

    can_write_openapi = can_write_base and _openapi_fields_default(omada_config)
    if can_write_openapi and _openapi_values_present(legacy):
        changed = _apply_openapi_fields(omada_config, legacy, key_path) or changed

    if changed:
        session.add(omada_config)
        session.commit()
    return changed


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
    result.omada_migrated = _migrate_omada_settings(legacy, session, key_path)
    if result.omada_migrated:
        logger.info("Migrated Omada settings from YAML/env sources.")
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
