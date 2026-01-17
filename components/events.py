# components/events.py
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from beanie.operators import Set, Inc
from data.models import User
from core.security import get_current_verified_user
from core.cache import SimpleCache
from core.translations import translate_text

router = APIRouter(prefix="/api/events", tags=["Events"])

# --- Configuration ---
# All events restart automatically.
# ID convention: event_{duration_days}d
EVENTS_CONFIG = {
    "event_1d": {
        "duration_days": 1,
        "entry_fee": 50,
        "name": "Daily Hustle",
        "description": "24 hours to prove you're the best!",
        "rewards": {"1": 500, "2": 250, "3": 100} # Rank: HC Amount
    },
    "event_2d": {
        "duration_days": 2,
        "entry_fee": 700,
        "name": "Weekend Warrior",
        "description": "48 hours of intense grinding.",
        "rewards": {"1": 1500, "2": 750, "3": 350}
    },
    "event_7d": {
        "duration_days": 7,
        "entry_fee": 2000,
        "name": "Weekly Tycoon",
        "description": "Dominate the week.",
        "rewards": {"1": 5000, "2": 2500, "3": 1000}
    },
    "event_14d": {
        "duration_days": 14,
        "entry_fee": 5000,
        "name": "Fortnight Legend",
        "description": "The ultimate endurance test.",
        "rewards": {"1": 15000, "2": 7500, "3": 3000}
    }
}

# In-memory cache for event leaderboards (updated/invalidated frequently or short TTL)
# Key: event_id, Value: SimpleCache instance
event_leaderboard_caches: dict[str, SimpleCache[List["EventLeaderboardEntry"]]] = {}


# --- DTOs ---

class EventInfo(BaseModel):
    event_id: str
    name: str
    description: str
    duration_days: int
    entry_fee: int
    start_time: datetime
    end_time: datetime
    participants_count: int = 0
    is_joined: bool = False
    current_rank_points: int = 0
    rewards_info: Dict[str, int]

class EventLeaderboardEntry(BaseModel):
    username: str
    rank_points: int
    level: int
    current_hustle: str

class JoinEventResponse(BaseModel):
    success: bool
    message: str
    new_balance: int
    event_id: str


# --- Helper Functions ---

def get_event_cycle_times(event_id: str) -> tuple[datetime, datetime]:
    """
    Calculates the current start and end time for a recurring event.
    Events assume a start epoch (e.g., beginning of 2024 or similar fixed point) 
    to ensure everyone sees the same cycle.
    For simplicity, we can align them to UTC midnight.
    """
    config = EVENTS_CONFIG.get(event_id)
    if not config:
        raise ValueError("Invalid event ID")
        
    duration_days = config["duration_days"]
    now = datetime.utcnow()
    
    # Calculate cycle number since a reference epoch (e.g. Jan 1 2024)
    epoch = datetime(2024, 1, 1)
    delta = now - epoch
    total_days = delta.days
    
    current_cycle_index = total_days // duration_days
    
    start_date = epoch + timedelta(days=current_cycle_index * duration_days)
    end_date = start_date + timedelta(days=duration_days)
    
    return start_date, end_date

from datetime import timedelta

async def get_event_participants_count(event_id: str) -> int:
    """Count users who have joined the current cycle of the event."""
    # This is an estimation. For exact count of *active* cycle participants, 
    # we might need to purge old joins or handle 'joined_at' check.
    # For now, we count everyone who has the key in 'joined_events'. 
    # Logic in background task should clear 'joined_events' on reset, so this is accurate.
    return await User.find(
        {f"joined_events.{event_id}": {"$exists": True}}
    ).count()


# --- Endpoints ---

@router.get("/list", response_model=List[EventInfo])
async def list_events(current_user: User = Depends(get_current_verified_user)):
    """List all available events with their status for the current user."""
    events_list = []
    
    for event_id, config in EVENTS_CONFIG.items():
        start_time, end_time = get_event_cycle_times(event_id)
        
        is_joined = event_id in current_user.joined_events
        current_points = current_user.events_points.get(event_id, 0)
        
        # Get participant count (could be optimized with a separate cached aggregator)
        count = await get_event_participants_count(event_id)
        
        events_list.append(EventInfo(
            event_id=event_id,
            name=translate_text(config["name"], current_user.language),
            description=translate_text(config["description"], current_user.language),
            duration_days=config["duration_days"],
            entry_fee=config["entry_fee"],
            start_time=start_time,
            end_time=end_time,
            participants_count=count,
            is_joined=is_joined,
            current_rank_points=current_points,
            rewards_info=config["rewards"]
        ))
        
    return events_list


@router.post("/join/{event_id}", response_model=JoinEventResponse)
async def join_event(
    event_id: str,
    current_user: User = Depends(get_current_verified_user)
):
    """Join an event by paying the entry fee."""
    config = EVENTS_CONFIG.get(event_id)
    if not config:
        raise HTTPException(status_code=404, detail="Event not found")
        
    if event_id in current_user.joined_events:
        raise HTTPException(status_code=400, detail="Already joined this event")
        
    if current_user.hc_balance < config["entry_fee"]:
        raise HTTPException(status_code=400, detail="Insufficient funds")
        
    # Deduct fee and mark as joined
    # We explicitly set rank points for this event to 0 to initialize it
    await current_user.update(
        Inc({User.hc_balance: -config["entry_fee"]}),
        Set({
            f"joined_events.{event_id}": datetime.utcnow(),
            f"events_points.{event_id}": 0 
        })
    )
    
    # Reload user to get new balance
    updated_user = await User.get(current_user.id)
    
    return JoinEventResponse(
        success=True,
        message=f"Successfully joined {config['name']}!",
        new_balance=updated_user.hc_balance,
        event_id=event_id
    )


async def _fetch_event_leaderboard(event_id: str) -> List[EventLeaderboardEntry]:
    """Fetch top 10 players for a specific event."""
    # Pipeline to find users who joined the event, sort by their event points
    pipeline = [
        {"$match": {f"events_points.{event_id}": {"$gt": 0}}},
        {"$sort": {f"events_points.{event_id}": -1}},
        {"$limit": 10},
        {
            "$project": {
                "username": 1,
                "events_points": 1,
                "level": 1,
                "current_hustle": 1
            }
        }
    ]
    
    collection = User.get_pymongo_collection()
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    return [
        EventLeaderboardEntry(
            username=doc["username"],
            rank_points=doc.get("events_points", {}).get(event_id, 0),
            level=doc["level"],
            current_hustle=doc.get("current_hustle", "Street Vendor")
        )
        for doc in results
    ]


@router.get("/leaderboard/{event_id}", response_model=List[EventLeaderboardEntry])
async def get_event_leaderboard(event_id: str):
    """Get the top 10 players for a specific event."""
    if event_id not in EVENTS_CONFIG:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # Get or create cache for this event
    if event_id not in event_leaderboard_caches:
        event_leaderboard_caches[event_id] = SimpleCache[List[EventLeaderboardEntry]](ttl_seconds=60)
    
    # Use a simple cache key wrapper
    async def fetcher():
        return await _fetch_event_leaderboard(event_id)
        
    return await event_leaderboard_caches[event_id].get_or_fetch(fetcher)
