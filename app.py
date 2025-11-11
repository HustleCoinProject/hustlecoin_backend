# app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from core.database import init_db
from components import users, tasks, leaderboard, hustles, shop, land, dev, tapping
from admin import admin_router
from admin.registry import auto_register_models

from datetime import datetime, timedelta, date


app = FastAPI(
    title="HustleCoin Backend",
    description="A clean, modular backend using FastAPI and Beanie ODM.",
    version="1.0.0"
)

# Mount static files for admin panel
app.mount("/admin/static", StaticFiles(directory="admin/static"), name="admin_static")

@app.on_event("startup")
async def on_startup():
    """Connect to the database when the app starts."""
    print("Initializing database connection...")
    await init_db()
    print("Database connection successful.")
    
    # Register admin models
    print("Registering admin models...")
    auto_register_models()
    print("Admin models registered.")

# --- Include Component Routers ---
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(leaderboard.router)
app.include_router(hustles.router)
app.include_router(shop.router)
app.include_router(land.router)
app.include_router(tapping.router)

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


@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the HustleCoin API v1!"}