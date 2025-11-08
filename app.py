# app.py
from fastapi import FastAPI
from core.database import init_db
from components import users, tasks, leaderboard, hustles, shop, land, dev, tapping

from datetime import datetime, timedelta, date


app = FastAPI(
    title="HustleCoin Backend",
    description="A clean, modular backend using FastAPI and Beanie ODM.",
    version="1.0.0"
)

@app.on_event("startup")
async def on_startup():
    """Connect to the database when the app starts."""
    print("Initializing database connection...")
    await init_db()
    print("Database connection successful.")

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


# Endpoint to get current server's timestamp {"timestamp": <current time> }
# it must be exactly same format so it appears like this in frontend: 2025-08-17 15:25:39.279
@app.get("/api/timestamp", response_model=dict)
async def get_server_time():
    """Returns the current server time in a specific format."""
    return {"timestamp": datetime.utcnow().isoformat()}


@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the HustleCoin API v1!"}