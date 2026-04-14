# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest portal configuration model."""

import json
from typing import Optional

from pydantic import field_validator
from sqlmodel import Column, Field, SQLModel, TEXT


class PortalConfig(SQLModel, table=True):
    """Guest portal configuration.

    Attributes:
        id: Primary key (integer, singleton record with id=1)
        success_redirect_url: Post-auth redirect URL (default: /guest/welcome)
        rate_limit_attempts: Max auth attempts per IP in window (1-1000, default: 5)
        rate_limit_window_seconds: Rolling window size in seconds (1-3600, default: 60)
        redirect_to_original_url: Redirect to original URL vs success page (default: True)
        trusted_proxy_networks: JSON list of trusted proxy networks in CIDR notation
            (default: ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"])
        session_idle_minutes: Guest session idle timeout in minutes (1-1440, default: 30)
        session_max_hours: Guest session max duration in hours (1-168, default: 8)
        guest_external_url: Guest portal external URL for captive detection (default: "")
    """

    __tablename__ = "portal_config"

    model_config = {"validate_assignment": True}

    id: int = Field(default=1, primary_key=True)
    success_redirect_url: str = Field(default="/guest/welcome", max_length=2048)
    rate_limit_attempts: int = Field(default=5, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    redirect_to_original_url: bool = Field(default=True)
    trusted_proxy_networks: Optional[str] = Field(
        default='["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]',
        sa_column=Column(TEXT),
    )
    session_idle_minutes: int = Field(default=30, ge=1, le=1440)
    session_max_hours: int = Field(default=8, ge=1, le=168)
    guest_external_url: str = Field(default="", max_length=2048)

    @field_validator("trusted_proxy_networks")
    @classmethod
    def validate_trusted_networks(cls, v: Optional[str]) -> Optional[str]:
        """Validate trusted_proxy_networks is valid JSON list."""
        if v is None:
            return '["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]'
        try:
            networks = json.loads(v)
            if not isinstance(networks, list):
                raise ValueError("trusted_proxy_networks must be a JSON list")
            if not all(isinstance(n, str) for n in networks):
                raise ValueError("All network entries must be strings")
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in trusted_proxy_networks: {e}") from e

    def get_trusted_networks(self) -> list[str]:
        """Get trusted proxy networks as a Python list."""
        if self.trusted_proxy_networks is None:
            return ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        networks: list[str] = json.loads(self.trusted_proxy_networks)
        return networks
