# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant REST API client."""

from typing import Any, Dict, List, Optional

import httpx
from fastapi import Request

from captive_portal.integrations.ha_errors import (
    HAAuthenticationError,
    HAConnectionError,
    HAServerError,
    HATimeoutError,
)


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

    async def get_all_states(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """Retrieve all entity states from Home Assistant.

        Args:
            timeout: Per-request timeout in seconds (overrides client default).

        Returns:
            List of entity state dicts (no filtering applied).

        Raises:
            HAConnectionError: When HA API is unreachable.
            HAAuthenticationError: On HTTP 401 responses.
            HAServerError: On HTTP 5xx responses.
            HATimeoutError: When the request times out.
        """
        url = f"{self.base_url}/states"

        try:
            response = await self.client.get(url, timeout=timeout)

            if response.status_code == 401:
                raise HAAuthenticationError(
                    user_message="Authentication with Home Assistant failed",
                    detail=f"HTTP 401 from {url}",
                )

            if response.status_code >= 500:
                raise HAServerError(
                    user_message="Home Assistant returned a server error",
                    detail=f"HTTP {response.status_code} from {url}",
                )

            response.raise_for_status()
            try:
                result: List[Dict[str, Any]] = response.json()
            except (ValueError, TypeError) as exc:
                raise HAServerError(
                    user_message="Home Assistant returned an invalid response",
                    detail=f"JSON decode error from {url}: {exc}",
                ) from exc
            return result

        except (
            HAAuthenticationError,
            HAServerError,
        ):
            raise
        except httpx.ConnectError as exc:
            raise HAConnectionError(
                user_message="Cannot connect to Home Assistant",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise HATimeoutError(
                user_message="Home Assistant request timed out",
                detail=str(exc),
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HAServerError(
                user_message="Home Assistant returned an unexpected error",
                detail=str(exc),
            ) from exc

    async def get_entity_registry(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """Retrieve all entity registry entries from Home Assistant.

        Calls the ``/config/entity_registry/list`` endpoint which
        returns metadata for every registered entity, including the
        ``platform`` that created it.

        Args:
            timeout: Per-request timeout in seconds (overrides
                client default).

        Returns:
            List of entity registry entry dicts.

        Raises:
            HAConnectionError: When HA API is unreachable.
            HAAuthenticationError: On HTTP 401 responses.
            HAServerError: On HTTP 5xx responses.
            HATimeoutError: When the request times out.
        """
        url = f"{self.base_url}/config/entity_registry/list"

        try:
            response = await self.client.get(url, timeout=timeout)

            if response.status_code == 401:
                raise HAAuthenticationError(
                    user_message="Authentication with Home Assistant failed",
                    detail=f"HTTP 401 from {url}",
                )

            if response.status_code >= 500:
                raise HAServerError(
                    user_message="Home Assistant returned a server error",
                    detail=f"HTTP {response.status_code} from {url}",
                )

            response.raise_for_status()
            try:
                result: List[Dict[str, Any]] = response.json()
            except (ValueError, TypeError) as exc:
                raise HAServerError(
                    user_message="Home Assistant returned an invalid response",
                    detail=f"JSON decode error from {url}: {exc}",
                ) from exc
            return result

        except (
            HAAuthenticationError,
            HAServerError,
        ):
            raise
        except httpx.ConnectError as exc:
            raise HAConnectionError(
                user_message="Cannot connect to Home Assistant",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise HATimeoutError(
                user_message="Home Assistant request timed out",
                detail=str(exc),
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HAServerError(
                user_message="Home Assistant returned an unexpected error",
                detail=str(exc),
            ) from exc

    async def get_timezone(self) -> str:
        """Fetch the configured timezone from Home Assistant.

        Returns:
            IANA timezone string (e.g., ``America/Los_Angeles``).
            Falls back to ``UTC`` when the config key is missing.

        Raises:
            HAConnectionError: When HA API is unreachable.
            HAAuthenticationError: On HTTP 401 responses.
            HAServerError: On HTTP 5xx responses or invalid JSON.
            HATimeoutError: When the request times out.
        """
        url = f"{self.base_url}/config"

        try:
            response = await self.client.get(url)

            if response.status_code == 401:
                raise HAAuthenticationError(
                    user_message="Authentication with Home Assistant failed",
                    detail=f"HTTP 401 from {url}",
                )

            if response.status_code >= 500:
                raise HAServerError(
                    user_message="Home Assistant returned a server error",
                    detail=f"HTTP {response.status_code} from {url}",
                )

            response.raise_for_status()
            try:
                data: Dict[str, Any] = response.json()
            except (ValueError, TypeError) as exc:
                raise HAServerError(
                    user_message="Home Assistant returned an invalid response",
                    detail=f"JSON decode error from {url}: {exc}",
                ) from exc
            time_zone = data.get("time_zone")
            if isinstance(time_zone, str):
                time_zone = time_zone.strip()
                if time_zone:
                    return time_zone
            return "UTC"

        except (
            HAAuthenticationError,
            HAServerError,
        ):
            raise
        except httpx.ConnectError as exc:
            raise HAConnectionError(
                user_message="Cannot connect to Home Assistant",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise HATimeoutError(
                user_message="Home Assistant request timed out",
                detail=str(exc),
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HAServerError(
                user_message="Home Assistant returned an unexpected error",
                detail=str(exc),
            ) from exc

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self.client.aclose()

    async def __aenter__(self) -> "HAClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        await self.close()


def get_ha_client(request: Request) -> "HAClient":
    """FastAPI dependency that returns the HAClient from app state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The HAClient instance stored on app.state during lifespan startup.
    """
    return request.app.state.ha_client  # type: ignore[no-any-return]
