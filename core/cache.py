# core/cache.py
"""
Simple in-memory caching utility with TTL (Time To Live) support.
Thread-safe for async operations using asyncio.Lock.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Awaitable, TypeVar, Generic, Optional

T = TypeVar('T')


class SimpleCache(Generic[T]):
    """
    Thread-safe in-memory cache with TTL.
    
    Usage:
        cache = SimpleCache(ttl_seconds=300)  # 5 minutes
        data = await cache.get_or_fetch(async_fetch_function)
    """
    
    def __init__(self, ttl_seconds: int):
        """
        Initialize cache with specified TTL.
        
        Args:
            ttl_seconds: Time to live in seconds before cache expires
        """
        self._cache = {
            "data": None,
            "last_updated": None,
            "lock": asyncio.Lock()
        }
        self.ttl_seconds = ttl_seconds
    
    async def get_or_fetch(self, fetch_func: Callable[[], Awaitable[T]]) -> T:
        """
        Get cached data or fetch fresh if expired.
        Uses double-check locking pattern to prevent race conditions.
        
        Args:
            fetch_func: Async function to call if cache is expired
            
        Returns:
            Cached or freshly fetched data
        """
        now = datetime.utcnow()
        
        # Quick check without lock (fast path)
        if (self._cache["data"] is not None and 
            self._cache["last_updated"] is not None and
            (now - self._cache["last_updated"]).total_seconds() < self.ttl_seconds):
            return self._cache["data"]
        
        # Cache invalid or expired, acquire lock
        async with self._cache["lock"]:
            # Double-check pattern - another request might have updated cache
            now = datetime.utcnow()
            if (self._cache["data"] is not None and 
                self._cache["last_updated"] is not None and
                (now - self._cache["last_updated"]).total_seconds() < self.ttl_seconds):
                return self._cache["data"]
            
            # Fetch fresh data
            fresh_data = await fetch_func()
            
            # Update cache
            self._cache["data"] = fresh_data
            self._cache["last_updated"] = now
            
            return fresh_data
    
    async def invalidate(self):
        """Manually clear the cache."""
        async with self._cache["lock"]:
            self._cache["data"] = None
            self._cache["last_updated"] = None
    
    def get_cache_info(self) -> dict:
        """Get cache metadata (for debugging/monitoring)."""
        return {
            "ttl_seconds": self.ttl_seconds,
            "last_updated": self._cache["last_updated"],
            "has_data": self._cache["data"] is not None,
            "age_seconds": (
                (datetime.utcnow() - self._cache["last_updated"]).total_seconds()
                if self._cache["last_updated"] else None
            )
        }
