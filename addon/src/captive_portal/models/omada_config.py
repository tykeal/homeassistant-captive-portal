# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Omada controller configuration model.

Stores the Omada controller connection settings as a singleton record
in the database.  The password is kept as Fernet-encrypted ciphertext
so it is never visible in plaintext database dumps.
"""

from sqlmodel import Field, SQLModel


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
