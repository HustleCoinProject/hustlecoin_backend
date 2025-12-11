# core/rate_limiter_slowapi.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
import redis.asyncio as redis
import asyncio
from core.config import settings

# Create Redis connection
try:
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=10,  # Increased timeout for cloud Redis
        socket_timeout=10,
        retry_on_timeout=True,
        health_check_interval=30  # Health check every 30 seconds
    )
except Exception:
    # Fallback to in-memory if Redis not available
    redis_client = None

# Redis state tracking for cleanup
_redis_was_down = False
_cleanup_lock = asyncio.Lock()

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL if redis_client else None,
    default_limits=["1000/hour"]  # Default fallback limit
)

# Custom key functions for different types of rate limiting
def get_user_id_key(request: Request) -> str:
    """Get user ID from authenticated request for user-specific limits."""
    # Try to get user from request state (set by auth dependency)
    user = getattr(request.state, 'user', None)
    if user:
        return f"user:{user.id}"
    # Fallback to IP if no user
    return f"ip:{get_remote_address(request)}"

def get_auth_key(request: Request) -> str:
    """Get key for auth endpoints (IP-based only)."""
    return f"auth:{get_remote_address(request)}"

def get_api_key(request: Request) -> str:
    """Get key for general API endpoints."""
    return f"api:{get_remote_address(request)}"

# Rate limit decorators for different endpoints
auth_limiter = Limiter(key_func=get_auth_key)
api_limiter = Limiter(key_func=get_api_key)
user_limiter = Limiter(key_func=get_user_id_key)

# Custom exception handler for consistent error responses
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Custom rate limit exceeded handler."""
    from fastapi.responses import JSONResponse
    from datetime import datetime
    
    # Get description from exc.detail or provide a default message
    description = getattr(exc, 'detail', None) or getattr(exc, 'description', 'Too many requests')
    retry_after = getattr(exc, 'retry_after', 60)
    
    return JSONResponse(
        status_code=429,
        content={
            "error": True,
            "message": f"Rate limit exceeded: {description}",
            "status_code": 429,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_after": retry_after
        },
        headers={"Retry-After": str(retry_after)}
    )

def setup_rate_limiting(app):
    """Setup SlowAPI rate limiting for the FastAPI app."""
    # Add SlowAPI middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    
    # Add custom rate limit exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    
    return app

# Health check for Redis connection with cleanup
async def check_redis_health():
    """Check if Redis is available for rate limiting and cleanup local memory if Redis reconnected."""
    global _redis_was_down
    
    try:
        if redis_client:
            await redis_client.ping()
            
            # Redis is healthy - check if it just came back online
            if _redis_was_down:
                await _cleanup_local_memory_on_redis_reconnect()
                _redis_was_down = False
            
            return True
    except Exception:
        _redis_was_down = True
        pass
    return False

async def _cleanup_local_memory_on_redis_reconnect():
    """Clean up local in-memory rate limit data when Redis reconnects."""
    async with _cleanup_lock:
        try:
            # Access SlowAPI's internal storage to clear local memory
            if hasattr(limiter, '_storage') and limiter._storage:
                # Check if using in-memory storage
                storage = limiter._storage
                if hasattr(storage, '_storage') and isinstance(storage._storage, dict):
                    old_size = len(storage._storage)
                    storage._storage.clear()
                    print(f"🧹 Cleaned up {old_size} local rate limit entries after Redis reconnection")
                    
            # Also cleanup individual limiter instances
            for limiter_instance in [auth_limiter, api_limiter, user_limiter]:
                if hasattr(limiter_instance, '_storage') and limiter_instance._storage:
                    storage = limiter_instance._storage
                    if hasattr(storage, '_storage') and isinstance(storage._storage, dict):
                        storage._storage.clear()
                        
        except Exception as e:
            print(f"⚠️ Error during local memory cleanup: {e}")