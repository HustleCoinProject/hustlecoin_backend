# components/rewards.py
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from beanie.operators import Pull, Push, Inc, Set, And
import math

from data.models import User, PendingReward
from core.security import get_current_verified_user
from core.rate_limiter_slowapi import api_limiter
from components.shop import clean_and_update_inventory
from data.models import InventoryItem
from components.shop import SHOP_ITEMS_CONFIG

router = APIRouter(prefix="/api/rewards", tags=["Rewards"])

class ClaimRewardResponse(BaseModel):
    success: bool
    message: str
    reward_type: str
    hc_amount: Optional[int] = None
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    new_hc_balance: int

@router.get("/pending", response_model=List[PendingReward])
@api_limiter.limit("60/minute")
async def get_pending_rewards(
    request: Request,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Get all pending rewards for the user.
    """
    return current_user.pending_rewards

@router.post("/claim/{reward_id}", response_model=ClaimRewardResponse)
@api_limiter.limit("15/minute")
async def claim_pending_reward(
    reward_id: str,
    request: Request,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Claim a specific pending reward by its ID.
    If it's HC, adds to balance. If it's an ITEM, adds to inventory.
    """
    # Find the target reward
    target_reward = next((r for r in current_user.pending_rewards if r.id == reward_id), None)
    
    if not target_reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reward not found or already claimed."
        )

    reward_item = target_reward.reward
    
    # Apply the reward
    if reward_item.reward_type == "HC" and reward_item.hc_amount:
        # Atomic update to remove reward and add HC
        update_result = await User.find_one(
            And(User.id == current_user.id, {"pending_rewards.id": reward_id})
        ).update(
            Pull({User.pending_rewards: {"id": reward_id}}),
            Inc({User.hc_balance: reward_item.hc_amount})
        )
        
        if not update_result:
             raise HTTPException(status_code=400, detail="Failed to claim reward.")
             
        await current_user.sync()
        
        return ClaimRewardResponse(
            success=True,
            message=f"Successfully claimed {reward_item.hc_amount} HC from {target_reward.source}",
            reward_type="HC",
            hc_amount=reward_item.hc_amount,
            new_hc_balance=current_user.hc_balance
        )
        
    elif reward_item.reward_type == "ITEM" and reward_item.item_id:
        # Get item config for expires_at computation
        item_config = SHOP_ITEMS_CONFIG.get(reward_item.item_id)
        if not item_config:
            raise HTTPException(status_code=400, detail="Invalid item ID in reward.")
            
        expires_at = None
        if "duration_seconds" in item_config.get("metadata", {}):
            from datetime import timedelta
            duration_seconds = item_config["metadata"]["duration_seconds"]
            expires_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
            
        new_item = InventoryItem(
            item_id=reward_item.item_id,
            quantity=reward_item.quantity,
            purchased_at=datetime.utcnow(),
            expires_at=expires_at
        )
        
        updated_inventory = clean_and_update_inventory(current_user.inventory, new_item)
        
        # Atomic update
        update_result = await User.find_one(
            And(User.id == current_user.id, {"pending_rewards.id": reward_id})
        ).update(
            Pull({User.pending_rewards: {"id": reward_id}}),
            Set({User.inventory: updated_inventory})
        )
        
        if not update_result:
             raise HTTPException(status_code=400, detail="Failed to claim item reward.")
             
        await current_user.sync()
        
        return ClaimRewardResponse(
            success=True,
            message=f"Successfully claimed {reward_item.item_name} from {target_reward.source}",
            reward_type="ITEM",
            item_id=reward_item.item_id,
            item_name=reward_item.item_name,
            new_hc_balance=current_user.hc_balance
        )
        
    else:
        raise HTTPException(status_code=400, detail="Invalid reward type.")
