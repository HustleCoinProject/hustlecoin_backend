# components/tasks.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from beanie.operators import Set, Inc

from core.security import get_current_user
from components.users import User

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

# --- DTOs ---
class BalanceUpdateResponse(BaseModel):
    message: str
    new_balance: int

# --- Endpoints ---
@router.post("/claim/ad-reward", response_model=BalanceUpdateResponse)
async def claim_ad_reward(current_user: User = Depends(get_current_user)):
    REWARD_AMOUNT = 100
    await current_user.update(Inc({User.hc_balance: REWARD_AMOUNT}))
    return {
        "message": "Reward claimed successfully",
        "new_balance": current_user.hc_balance + REWARD_AMOUNT
    }

@router.post("/claim/daily-tap", response_model=BalanceUpdateResponse)
async def claim_daily_tap(current_user: User = Depends(get_current_user)):
    REWARD_AMOUNT = 50
    if current_user.lastDailyTap and datetime.utcnow() < current_user.lastDailyTap + timedelta(hours=24):
        raise HTTPException(status_code=429, detail="Daily tap already claimed.")

    await current_user.update(
        Set({User.lastDailyTap: datetime.utcnow()}),
        Inc({User.hc_balance: REWARD_AMOUNT})
    )
    return {
        "message": "Daily tap claimed!",
        "new_balance": current_user.hc_balance + REWARD_AMOUNT
    }