# main.py
from fastapi import FastAPI
from core.database import init_db
from components import users, tasks, quizzes, leaderboard

app = FastAPI(
    title="HustleCoin Backend (Beanie Edition)",
    description="A clean, modular backend using FastAPI and Beanie ODM.",
    version="2.0.0"
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
app.include_router(quizzes.router)
app.include_router(leaderboard.router)

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the HustleCoin API v2!"}