# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Omada controller configuration model.

Stores the Omada controller connection settings as a singleton record
in the database.  The password is kept as Fernet-encrypted ciphertext
so it is never visible in plaintext database dumps.
"""

from pydantic import field_validator
from sqlmodel import Field, SQLModel

OPENAPI_MODES: tuple[str, str, str] = ("auto", "openapi", "legacy")


class OmadaConfig(SQLModel, table=True):
    """Omada controller connection configuration.

    Singleton record (``id=1``) that stores the controller URL,
    credentials, site name, controller ID, and SSL-verification
    preference.

    Attributes:
        id: Primary key (always 1 for the singleton record).
        controller_url: Omada controller URL (http/https).
        username: Hotspot operator username.
        encrypted_password: Fernet-encrypted password ciphertext.
        site_name: Omada site name (default: ``"Default"``).
        controller_id: Hex controller ID (auto-discovered when empty).
        verify_ssl: Whether to verify the controller's SSL certificate.
        client_id: OpenAPI application client identifier.
        encrypted_client_secret: Fernet-encrypted OpenAPI client secret.
        openapi_mode: Backend selection mode (auto, openapi, or legacy).
    """

    __tablename__ = "omada_config"

    model_config = {"validate_assignment": True}

    id: int = Field(default=1, primary_key=True)
    controller_url: str = Field(default="", max_length=2048)
    username: str = Field(default="", max_length=255)
    encrypted_password: str = Field(default="", max_length=1024)
    site_name: str = Field(default="Default", max_length=255)
    controller_id: str = Field(default="", max_length=64)
    verify_ssl: bool = Field(default=True)
    client_id: str = Field(default="", max_length=255)
    encrypted_client_secret: str = Field(default="", max_length=1024)
    openapi_mode: str = Field(default="auto", max_length=16)

    @field_validator("openapi_mode")
    @classmethod
    def _validate_openapi_mode(cls, value: str) -> str:
        """Validate OpenAPI backend mode values.

        Args:
            value: Candidate backend mode.

        Returns:
            Normalized backend mode.

        Raises:
            ValueError: If the mode is unsupported.
        """
        normalized = value.strip().lower()
        if normalized not in OPENAPI_MODES:
            supported = ", ".join(OPENAPI_MODES)
            raise ValueError(f"openapi_mode must be one of: {supported}")
        return normalized

    @property
    def omada_configured(self) -> bool:
        """True when URL, username, and encrypted_password are all non-empty.

        Returns:
            Whether all required connection fields are populated.
        """
        return bool(
            self.controller_url.strip()
            and self.username.strip()
            and self.encrypted_password.strip()
        )

    @property
    def legacy_credentials_present(self) -> bool:
        """Return whether legacy controller credentials are complete.

        Returns:
            True when URL, username, and encrypted password are present.
        """
        return self.omada_configured

    @property
    def openapi_configured(self) -> bool:
        """Return whether OpenAPI controller credentials are complete.

        Returns:
            True when URL, client ID, and encrypted client secret are present.
        """
        return bool(
            self.controller_url.strip()
            and self.client_id.strip()
            and self.encrypted_client_secret.strip()
        )

    @property
    def openapi_credentials_present(self) -> bool:
        """Return whether OpenAPI credentials are complete.

        Returns:
            True when OpenAPI credential fields can be used for probing.
        """
        return self.openapi_configured

    @property
    def missing_openapi_fields(self) -> tuple[str, ...]:
        """Return missing OpenAPI credential field names.

        Returns:
            Tuple of missing field names using operator-facing names.
        """
        missing: list[str] = []
        if not self.client_id.strip():
            missing.append("client_id")
        if not self.encrypted_client_secret.strip():
            missing.append("client_secret")
        return tuple(missing)

    @property
    def has_partial_openapi_credentials(self) -> bool:
        """Return whether some but not all OpenAPI credentials are set.

        Returns:
            True when exactly one OpenAPI credential is present.
        """
        has_client_id = bool(self.client_id.strip())
        has_secret = bool(self.encrypted_client_secret.strip())
        return has_client_id != has_secret
