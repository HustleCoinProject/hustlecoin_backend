# app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from core.database import init_db
from core.rate_limiter_slowapi import setup_rate_limiting, check_redis_health
from components import users, tasks, leaderboard, hustles, shop, land, dev, tapping, payouts, safe_lock, notifications, events
from admin import admin_router
from admin.registry import auto_register_models
from admin.background_tasks import reset_all_rank_points
from admin.event_tasks import check_event_resets

from prometheus_fastapi_instrumentator import Instrumentator

from datetime import datetime, timedelta, date
import asyncio
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize scheduler (will be started on app startup)
scheduler = AsyncIOScheduler()


app = FastAPI(
    title="HustleCoin Backend",
    description="A clean, modular backend using FastAPI and Beanie ODM.",
    version="1.0.0"
)

# Instrument the app with Prometheus
Instrumentator().instrument(app).expose(app)


# Configuration: Methods that strictly require the client key
# MODIFY HERE: Add "GET", "PUT", etc. to this set to protect them as well
PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"} 

# Define public paths that don't require the key (whitelist)
PUBLIC_PATHS = {
    "/docs", 
    "/redoc", 
    "/openapi.json", 
    "/health", 
    "/health/ready",
    "/metrics"
}

# Middleware to verify custom client key (stub)
@app.middleware("http")
async def verify_client_key(request: Request, call_next):
    # Always allow access to public paths and admin routes
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/admin"):
        return await call_next(request)
        
    # Only enforce check for specified methods
    if request.method in PROTECTED_METHODS:
        # Check for the custom header
        # User specified stub value: "scooby doo"
        client_key = request.headers.get("x-hustle-coin-client-key")
        if client_key != "scooby doo":
            return JSONResponse(
                status_code=403, 
                content={"detail": "Access denied: Missing or invalid client key"}
            )
        
    return await call_next(request)

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
        print("[SUCCESS] Redis connection successful - rate limiting active")
    else:
        print("[WARN] Redis connection failed - rate limiting will use in-memory fallback")
    
    # Register admin models
    print("Registering admin models...")
    auto_register_models()
    print("Admin models registered.")
    
    # Setup scheduled tasks
    print("Setting up scheduled tasks...")
    try:
        # Schedule weekly rank reset: Every Monday at midnight Angola time (WAT = UTC+1)
        angola_tz = pytz.timezone('Africa/Luanda')
        scheduler.add_job(
            reset_all_rank_points,
            trigger=CronTrigger(
                day_of_week='mon',  # Monday
                hour=0,             # Midnight
                minute=0,           # 00:00
                timezone=angola_tz
            ),
            id='weekly_rank_reset',
            name='Reset all user rank points to 0',
            replace_existing=True,
            max_instances=1  # Prevent concurrent executions in same instance
        )
        scheduler.start()
        logger.info("[SUCCESS] Scheduler started - Weekly rank reset scheduled for Mondays at 00:00 Angola time")
    except Exception as e:
        logger.error(f"[WARN] Failed to start scheduler: {e}")

    try:
        # Schedule Event Resets: Check every hour at minute 5 (to avoid conflict with daily global resets if any)
        scheduler.add_job(
            check_event_resets,
            trigger=CronTrigger(minute=5), 
            id='check_event_resets',
            name='Check for event completions and distribute rewards',
            replace_existing=True,
            max_instances=1
        )
        logger.info("[SUCCESS] Scheduler added - Event System Check")
    except Exception as e:
        logger.error(f"⚠️ Failed to add event scheduler: {e}")
    
    # Start background tasks
    print("Starting background tasks...")
    asyncio.create_task(redis_health_monitor())
    print("Background tasks started.")
    
    print("[SUCCESS] HustleCoin Backend is ready for production!")

@app.on_event("shutdown")
async def on_shutdown():
    """Clean shutdown of the application."""
    print("Shutting down HustleCoin Backend...")
    
    # Shutdown scheduler gracefully
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down successfully")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}")
    
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
app.include_router(safe_lock.router)
app.include_router(notifications.router)
app.include_router(events.router)

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
        "minimum_payout_kwanza": round(settings.MINIMUM_PAYOUT_HC / settings.PAYOUT_CONVERSION_RATE, 2),
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