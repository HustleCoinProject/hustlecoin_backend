# components/leaderboard.py
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel
from data.models import User
from core.cache import SimpleCache

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

# Cache for 5 minutes
leaderboard_cache = SimpleCache[List["LeaderboardEntry"]](ttl_seconds=300)

class LeaderboardEntry(BaseModel):
    username: str
    rank_points: int = 0  # Default to 0 for existing users without this field
    level: int
    hc_balance: int  # Still include for reference

async def _fetch_fresh_leaderboard() -> List[LeaderboardEntry]:
    """Fetch fresh leaderboard data from database using optimized query."""
    # Use aggregation pipeline for better performance
    pipeline = [
        {"$match": {"rank_points": {"$gt": 0}}},  # Only users with rank points
        {"$sort": {"rank_points": -1}},
        {"$limit": 10},
        {
            "$project": {
                "username": 1,
                "rank_points": 1,
                "level": 1,
                "hc_balance": 1
            }
        }
    ]
    
    collection = User.get_pymongo_collection()
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    return [
        LeaderboardEntry(
            username=doc["username"],
            rank_points=doc.get("rank_points", 0),
            level=doc["level"],
            hc_balance=doc["hc_balance"]
        )
        for doc in results
    ]

@router.get("", response_model=List[LeaderboardEntry])
async def get_leaderboard():
    """Get the top players ranked by their rank points with caching (5 minutes)."""
    return await leaderboard_cache.get_or_fetch(_fetch_fresh_leaderboard)