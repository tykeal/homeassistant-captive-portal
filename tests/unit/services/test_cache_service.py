# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for TTL cache service."""

import asyncio
from typing import Optional

import pytest

from captive_portal.services.cache_service import CacheService


class TestCacheService:
    """Test suite for CacheService."""

    @pytest.mark.asyncio
    async def test_cache_stores_and_retrieves_value(self) -> None:
        """Test basic cache get/set operations."""
        cache = CacheService(default_ttl_seconds=60)

        await cache.set("test_key", "test_value")
        result = await cache.get("test_key")

        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_cache_returns_none_for_missing_key(self) -> None:
        """Test cache returns None for non-existent keys."""
        cache = CacheService()

        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self) -> None:
        """Test cache entries expire after TTL."""
        cache = CacheService(default_ttl_seconds=1)

        await cache.set("test_key", "test_value")

        # Verify value exists
        result = await cache.get("test_key")
        assert result == "test_value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Value should be expired
        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_custom_ttl_overrides_default(self) -> None:
        """Test custom TTL overrides default TTL."""
        cache = CacheService(default_ttl_seconds=60)

        await cache.set("short_ttl", "value", ttl_seconds=1)

        await asyncio.sleep(1.1)

        result = await cache.get("short_ttl")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidate_removes_entry(self) -> None:
        """Test explicit invalidation removes cache entry."""
        cache = CacheService()

        await cache.set("test_key", "test_value")
        await cache.invalidate("test_key")

        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidate_nonexistent_key_succeeds(self) -> None:
        """Test invalidating non-existent key doesn't raise error."""
        cache = CacheService()

        # Should not raise
        await cache.invalidate("nonexistent")

    @pytest.mark.asyncio
    async def test_cache_invalidate_pattern_removes_matching_keys(self) -> None:
        """Test pattern-based invalidation removes all matching keys."""
        cache = CacheService()

        await cache.set("controller:omada1", "value1")
        await cache.set("controller:omada2", "value2")
        await cache.set("other:key", "value3")

        await cache.invalidate_pattern("controller:")

        # Controller keys should be gone
        assert await cache.get("controller:omada1") is None
        assert await cache.get("controller:omada2") is None

        # Other key should remain
        assert await cache.get("other:key") == "value3"

    @pytest.mark.asyncio
    async def test_cache_clear_removes_all_entries(self) -> None:
        """Test clear removes all cache entries."""
        cache = CacheService()

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        await cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    @pytest.mark.asyncio
    async def test_cache_cleanup_expired_removes_only_expired(self) -> None:
        """Test cleanup removes only expired entries."""
        cache = CacheService(default_ttl_seconds=1)

        # Set entries with different TTLs
        await cache.set("expired", "value1", ttl_seconds=0)  # Immediately expired
        await cache.set("valid", "value2", ttl_seconds=60)

        await asyncio.sleep(0.1)  # Let expired entry actually expire

        count = await cache.cleanup_expired()

        assert count == 1
        assert await cache.get("expired") is None
        assert await cache.get("valid") == "value2"

    @pytest.mark.asyncio
    async def test_cache_stores_complex_objects(self) -> None:
        """Test cache can store and retrieve complex objects."""
        cache = CacheService()

        test_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42,
        }

        await cache.set("complex", test_data)
        result = await cache.get("complex")

        assert result == test_data

    @pytest.mark.asyncio
    async def test_cache_concurrent_access_is_safe(self) -> None:
        """Test cache handles concurrent access safely."""
        cache = CacheService()

        async def set_value(key: str, value: str) -> None:
            """Set value in cache."""
            await cache.set(key, value)

        async def get_value(key: str) -> Optional[str]:
            """Get value from cache."""
            result = await cache.get(key)
            return result if isinstance(result, str) else None

        # Concurrent writes
        await asyncio.gather(
            set_value("key1", "value1"),
            set_value("key2", "value2"),
            set_value("key3", "value3"),
        )

        # Concurrent reads
        results = await asyncio.gather(
            get_value("key1"),
            get_value("key2"),
            get_value("key3"),
        )

        assert list(results) == ["value1", "value2", "value3"]
