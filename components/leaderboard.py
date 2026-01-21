# components/leaderboard.py
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from beanie import PydanticObjectId
from data.models import User, LeaderboardHistory
from core.cache import SimpleCache

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])

# Cache for 5 minutes
leaderboard_cache = SimpleCache[List["LeaderboardEntry"]](ttl_seconds=300)

class LeaderboardEntry(BaseModel):
    username: str
    rank_points: int = 0  # Default to 0 for existing users without this field
    level: int
    current_hustle: str
    hc_balance: int = 0  # Default to 0 if not present

class HistoryWeek(BaseModel):
    id: str
    week_start: datetime
    week_end: datetime
    entry_count: int

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
                "current_hustle": 1,
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
            current_hustle=doc.get("current_hustle", "Street Vendor"),
            hc_balance=doc.get("hc_balance", 0)
        )
        for doc in results
    ]

@router.get("", response_model=List[LeaderboardEntry])
async def get_leaderboard():
    """Get the top players ranked by their rank points with caching (5 minutes)."""
    return await leaderboard_cache.get_or_fetch(_fetch_fresh_leaderboard)

@router.get("/history-list", response_model=List[HistoryWeek])
async def get_history_list():
    """Get list of available past leaderboards."""
    histories = await LeaderboardHistory.find_all().sort(-LeaderboardHistory.week_end).to_list()
    return [
        HistoryWeek(
            id=str(h.id),
            week_start=h.week_start,
            week_end=h.week_end,
            entry_count=len(h.entries)
        )
        for h in histories
    ]

@router.get("/history/{history_id}", response_model=List[LeaderboardEntry])
async def get_history_detail(history_id: str):
    """Get a specific past leaderboard."""
    try:
        oid = PydanticObjectId(history_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
        
    history = await LeaderboardHistory.get(oid)
    if not history:
        raise HTTPException(status_code=404, detail="History not found")
        
    # Convert dict entries to LeaderboardEntry objects
    return [
        LeaderboardEntry(
            username=e["username"],
            rank_points=e.get("rank_points", 0),
            level=e.get("level", 1),
            current_hustle=e.get("current_hustle", "Street Vendor"),
            hc_balance=e.get("hc_balance", 0)
        )
        for e in history.entries
    ]