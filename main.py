from fastapi import FastAPI
from components import users, tasks, quizzes, leaderboard # Import the component routers

app = FastAPI(
    title="HustleCoin Backend",
    description="A modular backend where features are self-contained components.",
    version="1.0.0"
)

# --- Include Component Routers ---
# This is the "additive" part. To add a new feature, you just add its router here.
# To remove a feature, you comment out or delete its line.
app.include_router(users.router)
app.include_router(tasks.router)
# app.include_router(quizzes.router) # Example: quizzes are not ready, so we comment it out
# app.include_router(leaderboard.router)

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the HustleCoin API!"}
