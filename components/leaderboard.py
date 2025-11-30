# components/leaderboard.py
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel
from data.models import User
import asyncio
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

# In-memory cache for leaderboard
_leaderboard_cache = {
    "data": None,
    "last_updated": None,
    "lock": asyncio.Lock()
}

CACHE_DURATION_SECONDS = 60  # Cache for 1 minute

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
    """Get the top players ranked by their rank points with caching."""
    now = datetime.utcnow()
    
    # Check if cache is valid
    if (_leaderboard_cache["data"] is not None and 
        _leaderboard_cache["last_updated"] is not None and
        (now - _leaderboard_cache["last_updated"]).total_seconds() < CACHE_DURATION_SECONDS):
        return _leaderboard_cache["data"]
    
    # Cache is invalid, need to refresh
    async with _leaderboard_cache["lock"]:
        # Double-check pattern - another request might have updated cache
        if (_leaderboard_cache["data"] is not None and 
            _leaderboard_cache["last_updated"] is not None and
            (now - _leaderboard_cache["last_updated"]).total_seconds() < CACHE_DURATION_SECONDS):
            return _leaderboard_cache["data"]
        
        # Fetch fresh data
        fresh_data = await _fetch_fresh_leaderboard()
        
        # Update cache
        _leaderboard_cache["data"] = fresh_data
        _leaderboard_cache["last_updated"] = now
        
        return fresh_data