# components/leaderboard.py
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel
from .users import User

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

class LeaderboardEntry(BaseModel):
    username: str
    hc_balance: int
    level: int

@router.get("/", response_model=List[LeaderboardEntry])
async def get_leaderboard():
    top_users = await User.find(
        {},
        projection_model=LeaderboardEntry,
        sort=[("hc_balance", -1)],
        limit=10
    ).to_list()
    return top_users