import h3
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from core.rate_limiter_slowapi import api_limiter
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from beanie.operators import Inc, In, Set

from data.models import User, LandTile
from core.security import get_current_user
from core.game_logic import GameLogic
from core.config import settings

router = APIRouter(prefix="/api/land", tags=["Land System"])

# --- Game Configuration ---
MAP_RESOLUTION = 8

# --- DTOs ---
class TileInfo(BaseModel):
    h3_index: str
    owner_id: Optional[PydanticObjectId] = None

class MyLandTile(BaseModel):
    h3_index: str
    purchased_at: datetime
    purchase_price: int

class LandIncomeClaimResponse(BaseModel):
    message: str
    total_income: int
    tiles_processed: int
    new_balance: int
    next_claim_available_at: datetime

class LandIncomeStatus(BaseModel):
    can_claim: bool
    available_income: int
    tiles_count: int
    last_claim_at: Optional[datetime]
    next_claim_available_at: Optional[datetime]
    time_until_next_claim_seconds: Optional[int]

class LandConfig(BaseModel):
    land_price: int
    land_sell_price: int
    land_income_per_day: int
    income_accumulate: bool
    cooldown_hours: int

# --- Endpoints ---

@router.get("/tiles", response_model=List[TileInfo])
async def get_tiles_in_bbox(
    bbox: str = Query(..., description="Bounding box in format: minLng,minLat,maxLng,maxLat", 
                      example="-46.65,-23.58,-46.60,-23.52")
):
    """
    Get all OWNED H3 tiles within a given bounding box.
    This is used by the client to render the map view with only relevant tiles.
    """
    try:
        min_lng, min_lat, max_lng, max_lat = map(float, bbox.split(','))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid bbox format.")

    # Define the polygon for H3
    geojson_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [min_lng, min_lat], [max_lng, min_lat],
            [max_lng, max_lat], [min_lng, max_lat],
            [min_lng, min_lat] 
        ]]
    }

    # Get all potential H3 indexes within the polygon at the defined resolution
    h3_indexes = list(h3.geo_to_cells(geojson_polygon, MAP_RESOLUTION))

    if not h3_indexes:
        return []

    # Find which of these potential tiles are actually owned
    owned_tiles = await LandTile.find(
        In(LandTile.h3_index, h3_indexes)
    ).to_list()

    # --- FIX ---
    # The original code returned all h3_indexes, with null for unowned tiles.
    # The new code only returns the tiles that were found in the database (i.e., are owned).
    # This creates a much smaller and more useful response.
    return [
        TileInfo(h3_index=tile.h3_index, owner_id=tile.owner_id)
        for tile in owned_tiles
    ]


@router.get("/my-lands", response_model=List[MyLandTile])
async def get_my_lands(current_user: User = Depends(get_current_user)):
    """Retrieves all land tiles owned by the current user."""
    my_tiles = await LandTile.find(LandTile.owner_id == current_user.id).to_list()
    # Here you could add logic to check for 'land_multiplier' boosters in user inventory
    return my_tiles


@router.post("/buy/{h3_index}", status_code=status.HTTP_201_CREATED)
@api_limiter.limit("10/minute")
async def buy_land_tile(
    request: Request,
    h3_index: str, 
    current_user: User = Depends(get_current_user)
):
    """Purchases a single land tile for the current user."""
    if not h3.is_valid_cell(h3_index):
        raise HTTPException(status_code=400, detail="Invalid H3 tile index.")

    if current_user.hc_balance < settings.LAND_PRICE:
        raise HTTPException(status_code=402, detail="Insufficient HustleCoin to buy land.")
        
    # Award rank points for land purchase (5 points for investing in land)
    land_purchase_rank_points = await GameLogic.calculate_rank_point_reward(
        user=current_user,
        base_rank_points=5
    )
    
    # Check if tile is already owned
    existing_tile = await LandTile.find_one(LandTile.h3_index == h3_index)
    if existing_tile:
        raise HTTPException(status_code=409, detail="This land tile is already owned.")
    
    # Deduct balance and update rank points
    await current_user.update(
        Inc({
            User.hc_balance: -settings.LAND_PRICE,
            User.rank_points: land_purchase_rank_points
        })
    )
    
    # Create and save the new tile
    now = datetime.utcnow()
    new_tile = LandTile(
        h3_index=h3_index,
        owner_id=current_user.id,
        purchase_price=settings.LAND_PRICE,
        purchased_at=now,
        last_income_payout_at=now
    )
    
    try:
        await new_tile.insert()
    except Exception as e:
        # If insert fails (e.g., duplicate key), refund the user
        await current_user.update(
            Inc({
                User.hc_balance: settings.LAND_PRICE,
                User.rank_points: -land_purchase_rank_points
            })
        )
        # Check if it's a duplicate key error
        if "duplicate" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(status_code=409, detail="This land tile is already owned.")
        raise HTTPException(status_code=500, detail="Failed to purchase tile. Please try again.")

    return {
        "message": f"Land purchased successfully! Earned {land_purchase_rank_points} rank points.", 
        "h3_index": h3_index, 
        "new_balance": current_user.hc_balance - settings.LAND_PRICE,
        "rank_points_earned": land_purchase_rank_points,
        "new_rank_points": current_user.rank_points + land_purchase_rank_points
    }


@router.post("/sell/{h3_index}")
async def sell_land_tile(h3_index: str, current_user: User = Depends(get_current_user)):
    """Sells a land tile owned by the user back to the system."""
    tile_to_sell = await LandTile.find_one(
        LandTile.h3_index == h3_index,
        LandTile.owner_id == current_user.id
    )

    if not tile_to_sell:
        raise HTTPException(status_code=404, detail="You do not own this land tile.")

    # Atomically delete the tile and credit the user's account
    await tile_to_sell.delete()
    await current_user.update(Inc({User.hc_balance: settings.LAND_SELL_PRICE}))

    return {"message": "Land sold successfully!", "h3_index": h3_index, "new_balance": current_user.hc_balance + settings.LAND_SELL_PRICE}


@router.post("/claim-income", response_model=LandIncomeClaimResponse)
async def claim_land_income(current_user: User = Depends(get_current_user)):
    """
    Claims land income for all tiles owned by the user.
    Can only be claimed once every 24 hours.
    
    Income calculation depends on LAND_INCOME_ACCUMULATE setting:
    - If True: Income accumulates over time (wait longer = more income)
    - If False: Fixed daily amount regardless of wait time (default)
    
    FIRST CLAIM BONUS: For users who have never claimed land income before,
    they will always receive at least the full daily amount (50 HC per tile)
    regardless of how long they've owned the land. This prevents users from
    getting tiny amounts (e.g., 1 HC) on their first claim and then being
    locked out for 24 hours.
    """
    now = datetime.utcnow()
    
    # Check if user can claim (24 hours cooldown)
    if current_user.last_land_claim_at:
        time_since_last_claim = now - current_user.last_land_claim_at
        if time_since_last_claim < timedelta(hours=24):
            next_claim_time = current_user.last_land_claim_at + timedelta(hours=24)
            raise HTTPException(
                status_code=429, 
                detail=f"Land income can only be claimed once every 24 hours. Next claim available at: {next_claim_time.isoformat()}"
            )
    
    # Get all user's land tiles
    user_tiles = await LandTile.find(LandTile.owner_id == current_user.id).to_list()
    
    if not user_tiles:
        raise HTTPException(status_code=404, detail="You don't own any land tiles.")
    
    total_income = 0
    tiles_processed = 0
    
    # Calculate income for each tile
    for tile in user_tiles:
        # Calculate time since last claim or tile purchase (whichever is more recent)
        last_reference_time = tile.last_income_payout_at
        if current_user.last_land_claim_at and current_user.last_land_claim_at > last_reference_time:
            last_reference_time = current_user.last_land_claim_at
        
        time_diff_seconds = (now - last_reference_time).total_seconds()
        
        if time_diff_seconds > 0:
            # Calculate income based on accumulation setting
            if settings.LAND_INCOME_ACCUMULATE:
                # Accumulate income over the actual time passed
                tile_income = await GameLogic.calculate_land_income(
                    user=current_user,
                    time_diff_seconds=time_diff_seconds
                )
            else:
                # Fixed daily amount regardless of days passed (max 24 hours worth)
                # Cap the time at 24 hours (86400 seconds) for non-accumulating mode
                capped_time_seconds = min(time_diff_seconds, 24 * 3600)
                tile_income = await GameLogic.calculate_land_income(
                    user=current_user,
                    time_diff_seconds=capped_time_seconds
                )
                
                # FIRST CLAIM BONUS: If this is the user's first ever land claim,
                # ensure they get at least the full daily amount (50 HC per tile)
                if current_user.last_land_claim_at is None:
                    min_daily_income = await GameLogic.calculate_land_income(
                        user=current_user,
                        time_diff_seconds=24 * 3600  # Full day's worth
                    )
                    tile_income = max(tile_income, min_daily_income)
            
            total_income += tile_income
            tiles_processed += 1
            
            # Update tile's last payout time
            await tile.update(Set({LandTile.last_income_payout_at: now}))
    
    if total_income <= 0:
        raise HTTPException(status_code=400, detail="No income available to claim.")
    
    # Update user's balance, level earnings, and last claim time
    await current_user.update(
        Inc({User.hc_balance: total_income, User.hc_earned_in_level: total_income}),
        Set({User.last_land_claim_at: now})
    )
    
    # Calculate next claim time
    next_claim_available_at = now + timedelta(hours=24)
    
    return LandIncomeClaimResponse(
        message=f"Successfully claimed {total_income} HustleCoin from {tiles_processed} land tiles!",
        total_income=total_income,
        tiles_processed=tiles_processed,
        new_balance=current_user.hc_balance + total_income,
        next_claim_available_at=next_claim_available_at
    )


@router.get("/claim-status", response_model=LandIncomeStatus)
async def get_land_income_status(current_user: User = Depends(get_current_user)):
    """
    Gets the current status of land income claiming for the user.
    Shows available income, claim cooldown status, and timing information.
    
    Available income calculation depends on LAND_INCOME_ACCUMULATE setting:
    - If True: Shows accumulated income over actual time passed
    - If False: Shows max one day's worth of income (default)
    
    FIRST CLAIM BONUS: For users who have never claimed before, the available
    income will show at least the full daily amount (50 HC per tile) to
    ensure a good first-time user experience.
    """
    now = datetime.utcnow()
    
    # Get all user's land tiles
    user_tiles = await LandTile.find(LandTile.owner_id == current_user.id).to_list()
    
    tiles_count = len(user_tiles)
    
    if tiles_count == 0:
        return LandIncomeStatus(
            can_claim=False,
            available_income=0,
            tiles_count=0,
            last_claim_at=current_user.last_land_claim_at,
            next_claim_available_at=None,
            time_until_next_claim_seconds=None
        )
    
    # Check cooldown status
    can_claim = True
    next_claim_available_at = None
    time_until_next_claim_seconds = None
    
    if current_user.last_land_claim_at:
        time_since_last_claim = now - current_user.last_land_claim_at
        if time_since_last_claim < timedelta(hours=24):
            can_claim = False
            next_claim_available_at = current_user.last_land_claim_at + timedelta(hours=24)
            time_until_next_claim_seconds = int((next_claim_available_at - now).total_seconds())
    
    # Calculate available income
    total_available_income = 0
    
    for tile in user_tiles:
        # Calculate time since last claim or tile purchase (whichever is more recent)
        last_reference_time = tile.last_income_payout_at
        if current_user.last_land_claim_at and current_user.last_land_claim_at > last_reference_time:
            last_reference_time = current_user.last_land_claim_at
        
        time_diff_seconds = (now - last_reference_time).total_seconds()
        
        if time_diff_seconds > 0:
            # Calculate available income based on accumulation setting
            if settings.LAND_INCOME_ACCUMULATE:
                # Show accumulated income over the actual time passed
                tile_income = await GameLogic.calculate_land_income(
                    user=current_user,
                    time_diff_seconds=time_diff_seconds
                )
            else:
                # Show fixed daily amount regardless of days passed (max 24 hours worth)
                # Cap the time at 24 hours (86400 seconds) for non-accumulating mode
                capped_time_seconds = min(time_diff_seconds, 24 * 3600)
                tile_income = await GameLogic.calculate_land_income(
                    user=current_user,
                    time_diff_seconds=capped_time_seconds
                )
                
                # FIRST CLAIM BONUS: If this is the user's first ever land claim,
                # show at least the full daily amount (50 HC per tile)
                if current_user.last_land_claim_at is None:
                    min_daily_income = await GameLogic.calculate_land_income(
                        user=current_user,
                        time_diff_seconds=24 * 3600  # Full day's worth
                    )
                    tile_income = max(tile_income, min_daily_income)
            
            total_available_income += tile_income
    
    return LandIncomeStatus(
        can_claim=can_claim,
        available_income=total_available_income,
        tiles_count=tiles_count,
        last_claim_at=current_user.last_land_claim_at,
        next_claim_available_at=next_claim_available_at,
        time_until_next_claim_seconds=time_until_next_claim_seconds
    )


@router.get("/config", response_model=LandConfig)
async def get_land_config():
    """
    Gets the current land system configuration.
    Shows prices, income rates, and accumulation settings.
    """
    return LandConfig(
        land_price=settings.LAND_PRICE,
        land_sell_price=settings.LAND_SELL_PRICE,
        land_income_per_day=settings.LAND_INCOME_PER_DAY,
        income_accumulate=settings.LAND_INCOME_ACCUMULATE,
        cooldown_hours=24
    )