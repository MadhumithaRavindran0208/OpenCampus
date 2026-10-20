"""
Distributed Caching Layer (Redis with In-Memory fallback).

Provides:
- TTL-based key caching
- Tag-based cache invalidation (e.g. invalidate all 'projects' caches on create/update)
- Memoization decorator @cached(ttl=60, tag="projects")
- Graceful degradation if Redis is unavailable
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("opencampus.cache")

_redis_cache = None
_redis_initialized = False
_cache_lock = threading.Lock()

# In-memory LRU fallback store: key -> (value_json, expiry_monotonic)
_memory_cache: dict[str, tuple[str, float]] = {}
# Tag store: tag -> set of keys
_tag_keys: dict[str, set[str]] = {}


def _get_redis():
    global _redis_cache, _redis_initialized
    if not _redis_initialized:
        with _cache_lock:
            if not _redis_initialized:
                redis_url = os.environ.get("REDIS_URL", "").strip()
                if redis_url:
                    try:
                        import redis
                        _redis_cache = redis.from_url(redis_url, decode_responses=True)
                        _redis_cache.ping()
                        logger.info("Distributed Cache connected to Redis")
                    except Exception as exc:
                        logger.warning("Redis cache connection failed (%s); using in-memory cache", exc)
                        _redis_cache = None
                _redis_initialized = True
    return _redis_cache


class CacheEngine:
    @staticmethod
    def get(key: str) -> Any | None:
        r = _get_redis()
        if r is not None:
            try:
                val = r.get(f"cache:{key}")
                return json.loads(val) if val else None
            except Exception:
                pass

        with _cache_lock:
            if key in _memory_cache:
                val, expires_at = _memory_cache[key]
                if time.monotonic() < expires_at:
                    return json.loads(val)
                del _memory_cache[key]
        return None

    @staticmethod
    def set(key: str, value: Any, ttl: int = 60, tag: str | None = None) -> None:
        serialized = json.dumps(value, default=str)
        r = _get_redis()
        if r is not None:
            try:
                redis_key = f"cache:{key}"
                r.setex(redis_key, ttl, serialized)
                if tag:
                    r.sadd(f"cache_tag:{tag}", redis_key)
                return
            except Exception:
                pass

        with _cache_lock:
            _memory_cache[key] = (serialized, time.monotonic() + ttl)
            if tag:
                _tag_keys.setdefault(tag, set()).add(key)

    @staticmethod
    def invalidate_tag(tag: str) -> None:
        """Purge all cached entries tagged with `tag`."""
        r = _get_redis()
        if r is not None:
            try:
                tag_key = f"cache_tag:{tag}"
                keys = r.smembers(tag_key)
                if keys:
                    r.delete(*keys)
                r.delete(tag_key)
                logger.debug("Invalidated Redis cache tag: %s", tag)
            except Exception as exc:
                logger.warning("Failed to invalidate Redis cache tag %s: %s", tag, exc)

        with _cache_lock:
            keys = _tag_keys.pop(tag, set())
            for k in keys:
                _memory_cache.pop(k, None)


cache = CacheEngine()


def cached(ttl: int = 60, tag: str | None = None) -> Callable:
    """Decorator to cache return value of function based on arguments."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Build deterministic cache key
            raw_key = f"{func.__module__}:{func.__name__}:{args}:{sorted(kwargs.items())}"
            cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

            cached_val = cache.get(cache_key)
            if cached_val is not None:
                return cached_val

            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl, tag=tag)
            return result
        return wrapper
    return decorator
