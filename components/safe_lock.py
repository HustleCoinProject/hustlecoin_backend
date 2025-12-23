# components/safe_lock.py
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from core.rate_limiter_slowapi import api_limiter
from pydantic import BaseModel, Field
from beanie.operators import Inc, Set, And
import random

from data.models import User
from core.security import get_current_user, get_current_verified_user
from core.translations import translate_text
from components.shop import SHOP_ITEMS_CONFIG
from core.cache import SimpleCache

router = APIRouter(prefix="/api/safe-lock", tags=["Safe Lock"])

# Cache for aggregated global stats (5 minutes) - stores only totals, not user documents
# This is memory-efficient and scales to millions of users
class SafeLockAggregateStats(BaseModel):
    """Cached aggregate statistics for safe lock calculations."""
    total_rank_points: int
    total_safe_lock_amount: int
    total_users_with_safe_lock: int
    average_safe_lock_amount: float

safe_lock_global_cache = SimpleCache[SafeLockAggregateStats](ttl_seconds=300)

# --- DTOs (Data Transfer Objects) ---

class SafeLockStatusOut(BaseModel):
    """Response for safe lock status endpoint."""
    safe_lock_amount: int
    locked_until: datetime | None
    is_locked: bool
    can_claim: bool
    time_remaining_seconds: float | None = None
    total_safe_lock_global: int = Field(..., description="Total HC locked in safe by all users globally")

class SafeLockDepositRequest(BaseModel):
    """Request body for depositing HC to safe lock."""
    amount: int = Field(..., gt=0, description="Amount of HC to deposit (must be positive)")

class SafeLockDepositResponse(BaseModel):
    """Response for safe lock deposit endpoint."""
    success: bool
    message: str
    new_balance: int
    safe_lock_amount: int
    locked_until: datetime

class SafeLockReward(BaseModel):
    """Represents a reward item from safe lock claim."""
    reward_type: str  # "HC", "ITEM"
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    item_description: Optional[str] = None
    hc_amount: Optional[int] = None
    quantity: int = 1

class SafeLockClaimResponse(BaseModel):
    """Response for safe lock claim endpoint."""
    success: bool
    message: str
    returned_amount: int
    reward: SafeLockReward
    new_balance: int
    new_safe_lock_amount: int

class SafeLockGlobalStatsOut(BaseModel):
    """Response for global safe lock statistics (public endpoint)."""
    total_safe_lock_global: int = Field(..., description="Total HC locked in safe by all users")
    total_users_with_safe_lock: int = Field(..., description="Number of users with active safe locks")
    average_safe_lock_amount: float = Field(..., description="Average safe lock amount per user (excluding users with 0)")

# --- Helper Functions ---

async def _fetch_aggregate_stats() -> SafeLockAggregateStats:
    """
    Fetch aggregated statistics using MongoDB aggregation pipeline.
    This is memory-efficient as it only returns totals, not full user documents.
    Scales to millions of users.
    """
    collection = User.get_pymongo_collection()
    
    # Aggregation pipeline to calculate all needed statistics in one query
    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_rank_points": {"$sum": "$rank_points"},
                "total_safe_lock_amount": {"$sum": "$safe_lock_amount"},
                "total_users_with_safe_lock": {
                    "$sum": {"$cond": [{"$gt": ["$safe_lock_amount", 0]}, 1, 0]}
                },
                "sum_safe_lock_for_avg": {
                    "$sum": {"$cond": [{"$gt": ["$safe_lock_amount", 0]}, "$safe_lock_amount", 0]}
                }
            }
        }
    ]
    
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=1)
    
    if not results:
        # No users in database
        return SafeLockAggregateStats(
            total_rank_points=0,
            total_safe_lock_amount=0,
            total_users_with_safe_lock=0,
            average_safe_lock_amount=0.0
        )
    
    data = results[0]
    total_users_with_safe_lock = data.get("total_users_with_safe_lock", 0)
    
    # Calculate average (only among users with safe lock > 0)
    if total_users_with_safe_lock > 0:
        average = data.get("sum_safe_lock_for_avg", 0) / total_users_with_safe_lock
    else:
        average = 0.0
    
    return SafeLockAggregateStats(
        total_rank_points=data.get("total_rank_points", 0),
        total_safe_lock_amount=data.get("total_safe_lock_amount", 0),
        total_users_with_safe_lock=total_users_with_safe_lock,
        average_safe_lock_amount=round(average, 2)
    )


async def get_total_safe_lock_amount() -> int:
    """Calculate total HC locked in safe across all users (uses cached aggregated data)."""
    stats = await safe_lock_global_cache.get_or_fetch(_fetch_aggregate_stats)
    return stats.total_safe_lock_amount


async def calculate_safe_lock_reward(user: User) -> SafeLockReward:
    """
    Calculate reward based on user's rank points and safe lock amount relative to all other users.
    Ensures minimum 30 HC reward if calculation yields less.
    Uses cached aggregated statistics for memory-efficient performance.
    
    Returns a SafeLockReward with either HC or an item from shop.
    """
    # Get aggregated statistics (cached, memory-efficient)
    stats = await safe_lock_global_cache.get_or_fetch(_fetch_aggregate_stats)
    
    # Use aggregated totals
    total_rank_points = stats.total_rank_points
    total_safe_lock = stats.total_safe_lock_amount
    
    # Avoid division by zero
    if total_rank_points == 0:
        total_rank_points = 1
    if total_safe_lock == 0:
        total_safe_lock = 1
    
    # Calculate user's relative percentages
    rank_percentage = user.rank_points / total_rank_points
    safe_lock_percentage = user.safe_lock_amount / total_safe_lock
    
    # Combined weight (average of both percentages)
    combined_weight = (rank_percentage + safe_lock_percentage) / 2
    
    # Base reward calculation: scale from 30 to 500 HC based on weight
    # Top users (100% weight) get up to 500 HC, minimum is 30 HC
    base_reward_hc = int(30 + (combined_weight * 470))
    
    # Add bonus based on absolute safe lock amount (every 100 HC locked adds 5 HC reward)
    amount_bonus = int(user.safe_lock_amount / 100) * 5
    
    # Calculate final HC reward
    total_hc_reward = base_reward_hc + amount_bonus
    
    # Ensure minimum 30 HC
    total_hc_reward = max(30, total_hc_reward)
    
    # Determine if user gets an item or just HC
    # Higher combined weight = higher chance of getting items
    # Users with weight > 0.1 (top 10% activity) have chance for items
    
    if combined_weight > 0.1 and random.random() < 0.4:  # 40% chance for top users
        # Select a random item from shop as reward
        available_items = list(SHOP_ITEMS_CONFIG.values())
        
        # Weight selection towards less expensive items but include all
        # Create weighted pool: cheaper items appear more times
        weighted_pool = []
        for item in available_items:
            weight = max(1, 10 - (item["price"] // 100))  # Higher weight for cheaper items
            weighted_pool.extend([item] * weight)
        
        selected_item = random.choice(weighted_pool)
        
        return SafeLockReward(
            reward_type="ITEM",
            item_id=selected_item["item_id"],
            item_name=selected_item["name"],
            item_description=selected_item["description"],
            quantity=1
        )
    else:
        # Return HC reward
        return SafeLockReward(
            reward_type="HC",
            hc_amount=total_hc_reward
        )


# --- Endpoints ---

@router.get("/global-stats", response_model=SafeLockGlobalStatsOut)
@api_limiter.limit("60/minute")
async def get_global_safe_lock_stats(request: Request):
    """
    Public endpoint to get global safe lock statistics (cached for 5 minutes).
    Uses MongoDB aggregation for memory-efficient statistics calculation.
    No authentication required.
    """
    # Get aggregated statistics (cached, memory-efficient)
    stats = await safe_lock_global_cache.get_or_fetch(_fetch_aggregate_stats)
    
    return SafeLockGlobalStatsOut(
        total_safe_lock_global=stats.total_safe_lock_amount,
        total_users_with_safe_lock=stats.total_users_with_safe_lock,
        average_safe_lock_amount=stats.average_safe_lock_amount
    )

@router.get("/status", response_model=SafeLockStatusOut)
@api_limiter.limit("30/minute")
async def get_safe_lock_status(
    request: Request,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Get current safe lock status for the user.
    Returns locked amount, lock time, whether it can be claimed, and global statistics.
    """
    now = datetime.utcnow()
    
    is_locked = current_user.safe_lock_amount > 0
    can_claim = False
    time_remaining_seconds = None
    
    if is_locked and current_user.safe_lock_locked_until:
        can_claim = now >= current_user.safe_lock_locked_until
        if not can_claim:
            time_remaining_seconds = (current_user.safe_lock_locked_until - now).total_seconds()
    
    # Get global total for display
    total_global = await get_total_safe_lock_amount()
    
    return SafeLockStatusOut(
        safe_lock_amount=current_user.safe_lock_amount,
        locked_until=current_user.safe_lock_locked_until,
        is_locked=is_locked,
        can_claim=can_claim,
        time_remaining_seconds=time_remaining_seconds,
        total_safe_lock_global=total_global
    )


@router.post("/deposit", response_model=SafeLockDepositResponse)
@api_limiter.limit("10/minute")
async def deposit_to_safe_lock(
    request: Request,
    deposit_request: SafeLockDepositRequest,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Deposit HC to safe lock. Funds will be locked for 7 days.
    If depositing again before 7 days, the timer resets to 7 days from now.
    """
    amount = deposit_request.amount
    
    # Check if user has enough balance
    if current_user.hc_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient HC balance"
        )
    
    # Calculate new lock time (7 days from now)
    new_locked_until = datetime.utcnow() + timedelta(days=7)
    
    # Update user: deduct from balance, add to safe lock, update lock time
    await current_user.update(
        Inc({User.hc_balance: -amount, User.safe_lock_amount: amount}),
        Set({User.safe_lock_locked_until: new_locked_until})
    )
    
    # Refresh user data
    await current_user.sync()
    
    return SafeLockDepositResponse(
        success=True,
        message="HC deposited to safe lock successfully. Funds will be available in 7 days.",
        new_balance=current_user.hc_balance,
        safe_lock_amount=current_user.safe_lock_amount,
        locked_until=new_locked_until
    )


@router.post("/claim", response_model=SafeLockClaimResponse)
@api_limiter.limit("10/minute")
async def claim_safe_lock(
    request: Request,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Claim safe lock funds after 7 days have passed.
    Returns the locked amount plus a reward based on activity and amount.
    """
    now = datetime.utcnow()
    
    # Check if user has anything in safe lock
    if current_user.safe_lock_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No funds in safe lock"
        )
    
    # Check if lock period has passed
    if not current_user.safe_lock_locked_until or now < current_user.safe_lock_locked_until:
        time_remaining = None
        if current_user.safe_lock_locked_until:
            time_remaining = (current_user.safe_lock_locked_until - now).total_seconds()
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Safe lock is still locked. Time remaining: {int(time_remaining)} seconds" if time_remaining else "Safe lock is still locked"
        )
    
    # Calculate reward
    reward = await calculate_safe_lock_reward(current_user)
    
    # Calculate total amount to add to balance (principal + reward)
    returned_amount = current_user.safe_lock_amount
    hc_increase = returned_amount
    if reward.reward_type == "HC":
        hc_increase += reward.hc_amount
    
    # Prepare update operations
    # specific_ops = {}
    
    # If item reward, handle inventory update
    if reward.reward_type == "ITEM":
        # Add item to inventory logic...
        from data.models import InventoryItem
        from components.shop import clean_and_update_inventory
        
        # Get item config
        item_config = SHOP_ITEMS_CONFIG.get(reward.item_id)
        expires_at = None
        
        if item_config and "duration_seconds" in item_config.get("metadata", {}):
            duration_seconds = item_config["metadata"]["duration_seconds"]
            expires_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
        
        # Create new inventory item
        new_item = InventoryItem(
            item_id=reward.item_id,
            quantity=reward.quantity,
            purchased_at=datetime.utcnow(),
            expires_at=expires_at
        )
        
        # Clean and update inventory
        # We need to act on a copy of inventory since we might restart transaction if concurrency fails?
        # Ideally we'd do this inside a transaction, but Mongo atomic update is good enough here.
        updated_inventory = clean_and_update_inventory(current_user.inventory, new_item)
        
        # Atomically update user: Set safe lock to 0, Add balance, Set new inventory
        update_result = await User.find_one(
            And(User.id == current_user.id, User.safe_lock_amount > 0)
        ).update(
            Set({
                User.safe_lock_amount: 0,
                User.safe_lock_locked_until: None,
                User.inventory: updated_inventory
            }),
            Inc({User.hc_balance: hc_increase})
        )
    else:
        # Standard HC reward update
        # Atomically update user: Set safe lock to 0, Add balance
        update_result = await User.find_one(
            And(User.id == current_user.id, User.safe_lock_amount > 0)
        ).update(
            Set({
                User.safe_lock_amount: 0,
                User.safe_lock_locked_until: None
            }),
            Inc({User.hc_balance: hc_increase})
        )
    
    if not update_result:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to claim safe lock. It may have already been claimed."
        )
    
    # Refresh user data
    await current_user.sync()
    
    return SafeLockClaimResponse(
        success=True,
        message="Safe lock claimed successfully!",
        returned_amount=returned_amount,
        reward=reward,
        new_balance=current_user.hc_balance,
        new_safe_lock_amount=current_user.safe_lock_amount
    )
