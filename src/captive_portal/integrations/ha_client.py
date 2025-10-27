# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant REST API client."""

from typing import Any, Dict, Optional

import httpx


class HAClient:
    """Home Assistant REST API client for entity state retrieval.

    Uses httpx for async HTTP communication with Home Assistant.
    Designed for use in HA addon with Supervisor API access.

    Attributes:
        base_url: Base URL for HA API (e.g., http://supervisor/core/api)
        token: Bearer token for authentication
        client: Async HTTP client instance
    """

    def __init__(self, base_url: str, token: str) -> None:
        """Initialize HA client.

        Args:
            base_url: Base URL for HA API
            token: Authentication bearer token
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entity state from Home Assistant.

        Args:
            entity_id: Entity identifier (e.g., calendar.rental_control_test)

        Returns:
            Entity state dict with attributes, or None if not found

        Raises:
            Exception: On HTTP errors (5xx, connection failures)
        """
        url = f"{self.base_url}/states/{entity_id}"

        try:
            response = await self.client.get(url)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            result: Dict[str, Any] = response.json()
            return result

        except httpx.HTTPError as exc:
            raise Exception(f"HA API request failed: {exc}") from exc

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self.client.aclose()

    async def __aenter__(self) -> "HAClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        await self.close()
