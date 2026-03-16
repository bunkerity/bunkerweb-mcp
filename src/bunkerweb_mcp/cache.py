"""Caching layer for read-only BunkerWeb API operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiocache import Cache
from aiocache.serializers import JsonSerializer

# Initialize in-memory cache with JSON serialization
cache = Cache(Cache.MEMORY, serializer=JsonSerializer())


# Cache TTL configuration (in seconds)
CACHE_TTL = {
    "list_services": 300,  # 5 minutes
    "get_service": 300,  # 5 minutes
    "global_config_read": 600,  # 10 minutes
    "list_instances": 60,  # 1 minute
    "instance_get": 60,  # 1 minute
    "list_bans": 30,  # 30 seconds
    "configs_list": 300,  # 5 minutes
    "config_get": 300,  # 5 minutes
    "plugins_list": 600,  # 10 minutes
    "cache_list": 120,  # 2 minutes
    "jobs_list": 120,  # 2 minutes
}


async def get_cached(
    key: str,
    ttl: int,
    fetch_func: Callable[[], Any],
) -> Any:
    """Get value from cache or fetch and cache it.

    Args:
        key: Cache key
        ttl: Time-to-live in seconds
        fetch_func: Async function to fetch data on cache miss

    Returns:
        Cached or freshly fetched value
    """
    cached = await cache.get(key)
    if cached is not None:
        return cached

    value = await fetch_func()
    await cache.set(key, value, ttl=ttl)
    return value


async def invalidate_cache(pattern: str) -> None:
    """Invalidate cache entries matching the pattern.

    Args:
        pattern: Cache key pattern to invalidate (supports wildcards)
    """
    # Note: aiocache in-memory backend doesn't support pattern deletion
    # For simplicity, we clear the entire cache on mutations
    await cache.clear()
