# components/leaderboard.py
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel
from data.models import User

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

class LeaderboardEntry(BaseModel):
    username: str
    rank_points: int = 0  # Default to 0 for existing users without this field
    level: int
    hc_balance: int  # Still include for reference

@router.get("", response_model=List[LeaderboardEntry])
async def get_leaderboard():
    """Get the top players ranked by their rank points."""
    top_users = await User.find(
        {},
        projection_model=LeaderboardEntry,
        sort=[("rank_points", -1)],
        limit=10
    ).to_list()
    return top_users