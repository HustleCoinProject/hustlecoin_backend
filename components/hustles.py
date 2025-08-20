# components/hustles.py
from datetime import datetime, timedelta
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from beanie.operators import Set, Inc

from core.security import get_current_user
from core.translations import translate_text
from .users import User

router = APIRouter(prefix="/api/hustles", tags=["Hustles & Levels"])

# --- Hardcoded Game Configuration ---
# In a real application, this would be loaded from a database or a config file
# to allow the client to tweak it without a code change.
HUSTLE_CONFIG: Dict[int, List[str]] = {
    1: ["Street Vendor", "Cart Pusher", "Taxi Driver"],
    2: ["Shopkeeper", "Motorcycle Owner", "Small Farmer"],
    3: ["Secretary", "Store Owner", "Manager"],
    4: ["Minister", "Lawyer", "Business Director"],
    5: ["President", "CEO", "Hustle Legend"],
}

LEVEL_REQUIREMENTS: Dict[int, Dict[str, int]] = {
    # Key is the level you are trying to upgrade TO (so key 2 is for upgrading from 1 to 2)
    2: {"days_in_level": 3, "hc_earned": 1000, "upgrade_fee": 500},
    3: {"days_in_level": 5, "hc_earned": 5000, "upgrade_fee": 2500},
    4: {"days_in_level": 7, "hc_earned": 20000, "upgrade_fee": 10000},
    5: {"days_in_level": 10, "hc_earned": 100000, "upgrade_fee": 50000},
}

# --- DTOs (Data Transfer Objects) ---
class HustleSelect(BaseModel):
    hustle_name: str

class LevelStatusResponse(BaseModel):
    current_level: int
    current_hustle: Dict[str, str]  # Changed from str to Dict[str, str] for key-value pair
    days_in_level_progress: float # e.g., 2.5
    days_in_level_required: int
    hc_earned_in_level_progress: int
    hc_earned_in_level_required: int
    upgrade_fee: int
    is_eligible_for_upgrade: bool

class UpgradeResponse(BaseModel):
    message: str
    new_level: int
    new_hustle: Dict[str, str]  # Changed from str to Dict[str, str] for key-value pair

# --- Endpoints ---

def _localize_hustles(hustles: List[str], language: str = "en") -> Dict[str, str]:
    """Helper function to convert hustle list to localized key-value pairs."""
    return {hustle: translate_text(hustle, language) for hustle in hustles}

def _localize_hustle_config(language: str = "en") -> Dict[int, Dict[str, str]]:
    """Helper function to convert entire hustle config to localized key-value pairs."""
    return {
        level: _localize_hustles(hustles, language) 
        for level, hustles in HUSTLE_CONFIG.items()
    }


@router.get("/all", response_model=Dict[int, Dict[str, str]])
async def get_all_hustles(current_user: User = Depends(get_current_user)):
    """Lists all hustles in the game, grouped by level, with localized names."""
    return _localize_hustle_config(current_user.language)



@router.get("/available", response_model=Dict[str, str])
async def get_available_hustles_for_user(current_user: User = Depends(get_current_user)):
    """Gets the list of hustles for the user's current level with localized names."""
    available_hustles = HUSTLE_CONFIG.get(current_user.level, [])
    return _localize_hustles(available_hustles, current_user.language)



@router.post("/select")
async def select_hustle(hustle_data: HustleSelect, current_user: User = Depends(get_current_user)):
    """Allows a user to change their hustle within their current level."""
    available_hustles = HUSTLE_CONFIG.get(current_user.level, [])
    
    if hustle_data.hustle_name not in available_hustles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hustle '{hustle_data.hustle_name}' is not available at level {current_user.level}. Available: {available_hustles}"
        )

    await current_user.update(Set({User.current_hustle: hustle_data.hustle_name}))
    return {"message": f"Hustle changed to {hustle_data.hustle_name}"}




@router.get("/level-status", response_model=LevelStatusResponse)
async def get_level_status(current_user: User = Depends(get_current_user)):
    """Gets the user's current progress towards the next level upgrade."""
    next_level = current_user.level + 1
    requirements = LEVEL_REQUIREMENTS.get(next_level)

    # Create localized hustle key-value pair
    current_hustle_localized = {current_user.current_hustle: translate_text(current_user.current_hustle, current_user.language)}

    if not requirements:
        # User is at the max level
        return LevelStatusResponse(
            current_level=current_user.level,
            current_hustle=current_hustle_localized,
            days_in_level_progress=0, days_in_level_required=0,
            hc_earned_in_level_progress=current_user.hc_earned_in_level,
            hc_earned_in_level_required=0,
            upgrade_fee=0, is_eligible_for_upgrade=False
        )
    
    # Calculate progress
    days_in_level = (datetime.utcnow() - current_user.level_entry_date).total_seconds() / (24 * 3600)
    
    days_req_met = days_in_level >= requirements["days_in_level"]
    hc_earned_req_met = current_user.hc_earned_in_level >= requirements["hc_earned"]
    fee_req_met = current_user.hc_balance >= requirements["upgrade_fee"]

    return LevelStatusResponse(
        current_level=current_user.level,
        current_hustle=current_hustle_localized,
        days_in_level_progress=round(days_in_level, 2),
        days_in_level_required=requirements["days_in_level"],
        hc_earned_in_level_progress=current_user.hc_earned_in_level,
        hc_earned_in_level_required=requirements["hc_earned"],
        upgrade_fee=requirements["upgrade_fee"],
        is_eligible_for_upgrade=(days_req_met and hc_earned_req_met and fee_req_met)
    )




@router.post("/level-upgrade", response_model=UpgradeResponse)
async def upgrade_user_level(current_user: User = Depends(get_current_user)):
    """Attempts to upgrade the user's level if they meet all criteria."""
    status_response = await get_level_status(current_user=current_user)
    
    if not status_response.is_eligible_for_upgrade:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upgrade requirements not met."
        )
    
    next_level = current_user.level + 1
    upgrade_fee = status_response.upgrade_fee
    
    # Reset for the new level
    new_hustle = HUSTLE_CONFIG[next_level][0] # Default to the first hustle of the new level
    new_hustle_localized = {new_hustle: translate_text(new_hustle, current_user.language)}
    
    await current_user.update(
        Inc({User.hc_balance: -upgrade_fee}),
        Set({
            User.level: next_level,
            User.current_hustle: new_hustle,
            User.level_entry_date: datetime.utcnow(),
            User.hc_earned_in_level: 0 # Reset the earnings counter
        })
    )
    
    return UpgradeResponse(
        message=f"Congratulations! You have been promoted to Level {next_level}.",
        new_level=next_level,
        new_hustle=new_hustle_localized
    )