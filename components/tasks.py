from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import get_db_context, AppContext
from core.security import get_current_user

# --- Router ---
router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

# --- Models ---
class BalanceUpdateResponse(BaseModel):
    message: str
    new_balance: int

# --- Utility for managing balance changes ---
async def update_balance_and_log(db_ctx: AppContext, user_id: ObjectId, amount: int, type: str, description: str):
    user = await db_ctx.users_collection.find_one({"_id": user_id})
    before_balance = user["hc_balance"]
    new_balance = before_balance + amount

    await db_ctx.users_collection.update_one({"_id": user_id}, {"$set": {"hc_balance": new_balance}})
    await db_ctx.transactions_collection.insert_one({
        "userId": user_id, "amount": amount, "type": type, "description": description,
        "before_balance": before_balance, "after_balance": new_balance,
        "timestamp": datetime.utcnow()
    })
    return new_balance

# --- Endpoints ---
@router.post("/claim/ad-reward", response_model=BalanceUpdateResponse)
async def claim_ad_reward(
    current_user: dict = Depends(get_current_user),
    db_ctx: AppContext = Depends(get_db_context)
):
    REWARD_AMOUNT = 100
    new_balance = await update_balance_and_log(
        db_ctx, current_user["_id"], REWARD_AMOUNT, "ad_reward", "Reward for watching ad"
    )
    return {"message": "Reward claimed successfully", "new_balance": new_balance}

@router.post("/claim/daily-tap", response_model=BalanceUpdateResponse)
async def claim_daily_tap(
    current_user: dict = Depends(get_current_user),
    db_ctx: AppContext = Depends(get_db_context)
):
    REWARD_AMOUNT = 50
    last_tap = current_user.get("lastDailyTap")
    
    if last_tap and datetime.utcnow() < last_tap + timedelta(hours=24):
        raise HTTPException(status_code=429, detail="Daily tap already claimed.")

    await db_ctx.users_collection.update_one({"_id": current_user["_id"]}, {"$set": {"lastDailyTap": datetime.utcnow()}})
    new_balance = await update_balance_and_log(
        db_ctx, current_user["_id"], REWARD_AMOUNT, "daily_tap", "Daily tap bonus"
    )
    return {"message": "Daily tap claimed!", "new_balance": new_balance}