# app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from core.database import init_db
from core.rate_limiter_slowapi import setup_rate_limiting, check_redis_health
from components import users, tasks, leaderboard, hustles, shop, land, dev, tapping, payouts
from admin import admin_router
from admin.registry import auto_register_models

from datetime import datetime, timedelta, date
import asyncio
from contextlib import asynccontextmanager


app = FastAPI(
    title="HustleCoin Backend",
    description="A clean, modular backend using FastAPI and Beanie ODM.",
    version="1.0.0"
)

# Setup rate limiting
setup_rate_limiting(app)

# Mount static files for admin panel
app.mount("/admin/static", StaticFiles(directory="admin/static"), name="admin_static")

# Background task for Redis health monitoring with cleanup
async def redis_health_monitor():
    """Background task to monitor Redis connection and cleanup local memory when Redis reconnects."""
    # Wait a bit on startup to allow Redis connection to establish
    await asyncio.sleep(10)
    startup_check_done = False
    
    while True:
        try:
            redis_healthy = await check_redis_health()
            
            # Only show warning after startup grace period
            if not redis_healthy and startup_check_done:
                print("⚠️ Redis connection lost - rate limiting falling back to in-memory")
            elif not redis_healthy and not startup_check_done:
                print("🔄 Waiting for Redis connection to establish...")
            
            startup_check_done = True
            await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            print(f"Redis health check error: {e}")
            await asyncio.sleep(60)  # Retry in 1 minute on error

@app.on_event("startup")
async def on_startup():
    """Initialize the application on startup."""
    print("Initializing database connection...")
    await init_db()
    print("Database connection successful.")
    
    # Test Redis connection
    print("Testing Redis connection...")
    redis_status = await check_redis_health()
    if redis_status:
        print("✅ Redis connection successful - rate limiting active")
    else:
        print("⚠️ Redis connection failed - rate limiting will use in-memory fallback")
    
    # Register admin models
    print("Registering admin models...")
    auto_register_models()
    print("Admin models registered.")
    
    # Start background tasks
    print("Starting background tasks...")
    asyncio.create_task(redis_health_monitor())
    print("Background tasks started.")
    
    print("🚀 HustleCoin Backend is ready for production!")

@app.on_event("shutdown")
async def on_shutdown():
    """Clean shutdown of the application."""
    print("Shutting down HustleCoin Backend...")
    # Add any cleanup tasks here
    print("Shutdown complete.")

# --- Include Component Routers ---
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(leaderboard.router)
app.include_router(hustles.router)
app.include_router(shop.router)
app.include_router(land.router)
app.include_router(tapping.router)
app.include_router(payouts.router)

# Add the dev router here
app.include_router(dev.router)

# Include admin router
app.include_router(admin_router)


# Endpoint to get current server's timestamp {"timestamp": <current time> }
# it must be exactly same format so it appears like this in frontend: 2025-08-17 15:25:39.279
@app.get("/api/timestamp", response_model=dict)
async def get_server_time():
    """Returns the current server time in a specific format."""
    return {"timestamp": datetime.utcnow().isoformat()}


@app.get("/api/system/info", response_model=dict)
async def get_system_info():
    """Returns system information including payout conversion rates."""
    from core.config import settings
    return {
        "payout_conversion_rate": settings.PAYOUT_CONVERSION_RATE,
        "minimum_payout_hc": settings.MINIMUM_PAYOUT_HC,
        "minimum_payout_kwanza": settings.MINIMUM_PAYOUT_KWANZA,
        "land_price": settings.LAND_PRICE,
        "land_income_per_day": settings.LAND_INCOME_PER_DAY
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers."""
    try:
        # Test database connection
        from data.models import User
        await User.count()
        
        # Check Redis health
        redis_status = "connected" if await check_redis_health() else "disconnected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "database": "connected",
            "redis": redis_status
        }
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": "Database connection failed"
            }
        )

@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check for Kubernetes deployments."""
    try:
        # More thorough checks can be added here
        from data.models import User
        await User.count()
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "ready",
                "api": "ready",
                "redis": "ready" if await check_redis_health() else "degraded"
            }
        }
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Service not ready")

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the HustleCoin API v1!"}