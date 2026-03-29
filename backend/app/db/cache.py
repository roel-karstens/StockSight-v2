"""
cache.py — Redis cache helpers.

Provides async get/set/delete with JSON serialisation and configurable TTL.
All functions are fault-tolerant: they log warnings but never raise.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

# Singleton Redis client
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the singleton async Redis client."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis


async def cache_get(key: str) -> dict | list | None:
    """Retrieve a cached JSON value by key. Returns None on miss or error."""
    try:
        redis = await get_redis()
        data = await redis.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.warning(f"cache_get({key}) failed: {e}")
        return None


async def cache_set(key: str, value: dict | list, ttl: int = 3600) -> None:
    """Store a JSON value in cache with a TTL (seconds)."""
    try:
        redis = await get_redis()
        await redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.warning(f"cache_set({key}) failed: {e}")


async def cache_delete(key: str) -> None:
    """Delete a cached value by key."""
    try:
        redis = await get_redis()
        await redis.delete(key)
    except Exception as e:
        logger.warning(f"cache_delete({key}) failed: {e}")
