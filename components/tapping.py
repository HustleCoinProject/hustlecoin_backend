# components/tapping.py
from datetime import datetime, date, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from beanie.operators import Inc, Set

from data.models import User
from core.security import get_current_user
from core.game_logic import GameLogic

router = APIRouter(prefix="/api/tapping", tags=["Tapping System"])

# --- Configuration ---
DAILY_TAP_LIMIT = 200  # Maximum HC that can be earned per day from tapping
TAP_RESET_HOUR = 0  # Hour when daily limit resets (24-hour format, UTC)

# --- DTOs (Data Transfer Objects) ---
class TapRequest(BaseModel):
    tap_count: int = Field(..., ge=1, le=100, description="Number of taps in this batch (1-100)")

class TapResponse(BaseModel):
    success: bool
    message: str
    hc_earned: int
    rank_points_earned: int
    new_balance: int
    new_rank_points: int
    daily_earnings: int
    daily_limit: int
    remaining_taps: int
    next_reset_at: datetime | None = None

class TapStatusResponse(BaseModel):
    daily_earnings: int
    daily_limit: int
    remaining_taps: int
    can_tap: bool
    next_reset_at: datetime | None = None

# --- Helper Functions ---
def get_next_reset_time() -> datetime:
    """Calculate the next reset time (next day at TAP_RESET_HOUR UTC)"""
    now = datetime.utcnow()
    next_reset = now.replace(hour=TAP_RESET_HOUR, minute=0, second=0, microsecond=0)
    
    # If current time is past the reset hour, move to next day
    if now.hour >= TAP_RESET_HOUR:
        next_reset += timedelta(days=1)
    
    return next_reset

def should_reset_daily_taps(user: User) -> bool:
    """Check if user's daily tap earnings should be reset"""
    today = date.today()
    return user.last_tap_reset_date != today

@router.post("/tap", response_model=TapResponse)
async def process_tap_batch(
    tap_request: TapRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Process a batch of taps and award HC based on daily limits.
    Each tap awards 1 HC, but requests are processed in batches for efficiency.
    """
    
    today = date.today()
    updates_to_set = {}
    
    # Reset daily earnings if it's a new day
    if should_reset_daily_taps(current_user):
        current_user.daily_tap_earnings = 0
        current_user.last_tap_reset_date = today
        updates_to_set[User.daily_tap_earnings] = 0
        updates_to_set[User.last_tap_reset_date] = today
    
    # Calculate how many HC can be earned
    remaining_limit = DAILY_TAP_LIMIT - current_user.daily_tap_earnings
    
    if remaining_limit <= 0:
        # Daily limit reached
        next_reset_at = get_next_reset_time()
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Daily tap limit reached. Try again tomorrow!",
                "next_reset_at": next_reset_at.isoformat(),
                "daily_earnings": current_user.daily_tap_earnings,
                "daily_limit": DAILY_TAP_LIMIT
            }
        )
    
    # Calculate actual HC to award (capped by remaining limit)
    base_hc_to_award = min(tap_request.tap_count, remaining_limit)
    
    if base_hc_to_award <= 0:
        # No HC can be awarded
        next_reset_at = get_next_reset_time()
        return TapResponse(
            success=False,
            message="Daily tap limit reached. Try again tomorrow!",
            hc_earned=0,
            new_balance=current_user.hc_balance,
            daily_earnings=current_user.daily_tap_earnings,
            daily_limit=DAILY_TAP_LIMIT,
            remaining_taps=0,
            next_reset_at=next_reset_at
        )
    
    # Apply game logic bonuses (level multiplier, boosters, etc.)
    final_hc_reward = await GameLogic.calculate_task_reward(
        user=current_user,
        base_reward=base_hc_to_award
    )
    
    # Calculate rank points (1 rank point per 20 taps, minimum 1 per session)
    base_rank_points = max(1, base_hc_to_award // 20)
    final_rank_points = await GameLogic.calculate_rank_point_reward(
        user=current_user,
        base_rank_points=base_rank_points
    )
    
    # Update user's balance, rank points, and daily tap earnings
    new_daily_earnings = current_user.daily_tap_earnings + base_hc_to_award
    updates_to_set[User.daily_tap_earnings] = new_daily_earnings
    
    await current_user.update(
        Inc({
            User.hc_balance: final_hc_reward, 
            User.hc_earned_in_level: final_hc_reward,
            User.rank_points: final_rank_points
        }),
        Set(updates_to_set)
    )
    
    # Calculate remaining taps for response
    remaining_taps = max(0, DAILY_TAP_LIMIT - new_daily_earnings)
    next_reset_at = get_next_reset_time() if remaining_taps == 0 else None
    
    return TapResponse(
        success=True,
        message=f"Successfully processed {tap_request.tap_count} taps! Earned {final_hc_reward} HC and {final_rank_points} rank points.",
        hc_earned=final_hc_reward,
        rank_points_earned=final_rank_points,
        new_balance=current_user.hc_balance + final_hc_reward,
        new_rank_points=current_user.rank_points + final_rank_points,
        daily_earnings=new_daily_earnings,
        daily_limit=DAILY_TAP_LIMIT,
        remaining_taps=remaining_taps,
        next_reset_at=next_reset_at
    )


@router.get("/status", response_model=TapStatusResponse)
async def get_tap_status(current_user: User = Depends(get_current_user)):
    """Get current tapping status for the user."""
    today = date.today()
    
    # Reset daily earnings if it's a new day
    if should_reset_daily_taps(current_user):
        daily_earnings = 0
    else:
        daily_earnings = current_user.daily_tap_earnings
    
    remaining_taps = max(0, DAILY_TAP_LIMIT - daily_earnings)
    can_tap = remaining_taps > 0
    next_reset_at = get_next_reset_time() if not can_tap else None
    
    return TapStatusResponse(
        daily_earnings=daily_earnings,
        daily_limit=DAILY_TAP_LIMIT,
        remaining_taps=remaining_taps,
        can_tap=can_tap,
        next_reset_at=next_reset_at
    )
