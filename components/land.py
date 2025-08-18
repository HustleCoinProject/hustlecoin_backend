import h3
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from beanie import Document, PydanticObjectId, Indexed
from beanie.operators import Inc,In

from core.security import get_current_user
from .users import User

router = APIRouter(prefix="/api/land", tags=["Land System"])

# --- Game Configuration ---
LAND_PRICE = 500  # Price in HustleCoin to buy one tile
LAND_SELL_PRICE = 400 # Price for selling a tile back to the system
MAP_RESOLUTION = 8

LAND_INCOME_PER_DAY = 50
LAND_INCOME_PER_SECOND = LAND_INCOME_PER_DAY / (24 * 3600)

# --- Beanie Document Model ---
class LandTile(Document):
    h3_index: Indexed(str, unique=True)
    owner_id: Indexed(PydanticObjectId)
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    purchase_price: int = LAND_PRICE
    last_income_payout_at: datetime = Field(default_factory=datetime.utcnow)


    class Settings:
        name = "land_tiles"

# --- DTOs ---
class TileInfo(BaseModel):
    h3_index: str
    owner_id: Optional[PydanticObjectId] = None

class MyLandTile(BaseModel):
    h3_index: str
    purchased_at: datetime
    purchase_price: int

# --- Endpoints ---

@router.get("/tiles", response_model=List[TileInfo])
async def get_tiles_in_bbox(
    bbox: str = Query(..., description="Bounding box in format: minLng,minLat,maxLng,maxLat", 
                      example="-46.65,-23.58,-46.60,-23.52")
):
    """
    Get all H3 tiles and their ownership status within a given bounding box.
    Used by the client to render the map view.
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

    # Get all H3 indexes within the polygon at the defined resolution
    h3_indexes = list(h3.geo_to_cells(geojson_polygon, MAP_RESOLUTION))

    if not h3_indexes:
        return []

    # Find which of these tiles are already owned
    owned_tiles = await LandTile.find(
        In(LandTile.h3_index, h3_indexes)
    ).to_list()
    owned_map = {tile.h3_index: tile.owner_id for tile in owned_tiles}

    # Prepare the response
    response_tiles = [
        TileInfo(h3_index=index, owner_id=owned_map.get(index))
        for index in h3_indexes
    ]
    return response_tiles

@router.get("/my-lands", response_model=List[MyLandTile])
async def get_my_lands(current_user: User = Depends(get_current_user)):
    """Retrieves all land tiles owned by the current user."""
    my_tiles = await LandTile.find(LandTile.owner_id == current_user.id).to_list()
    # Here you could add logic to check for 'land_multiplier' boosters in user inventory
    return my_tiles


@router.post("/buy/{h3_index}", status_code=status.HTTP_201_CREATED)
async def buy_land_tile(h3_index: str, current_user: User = Depends(get_current_user)):
    """Purchases a single land tile for the current user."""
    if not h3.is_valid_cell(h3_index):
        raise HTTPException(status_code=400, detail="Invalid H3 tile index.")

    if current_user.hc_balance < LAND_PRICE:
        raise HTTPException(status_code=402, detail="Insufficient HustleCoin to buy land.")
        
    # Check if tile is already owned
    if await LandTile.find_one(LandTile.h3_index == h3_index):
        raise HTTPException(status_code=409, detail="This land tile is already owned.")

    # Deduct cost and create the land tile
    # Note: In a high-concurrency system, this two-step process has a small race condition risk.
    # A more robust solution might use MongoDB transactions for multi-document atomicity.
    
    await current_user.update(Inc({User.hc_balance: -LAND_PRICE}))
    

    now = datetime.utcnow()
    new_tile = LandTile(
        h3_index=h3_index,
        owner_id=current_user.id,
        purchase_price=LAND_PRICE,
        purchased_at=now,
        last_income_payout_at=now # ### EXPLICITLY SET ###
    )

    try:
        await new_tile.create()
    except Exception:
        # Compensating action: Refund the user if tile creation fails (e.g., duplicate key on race)
        await current_user.update(Inc({User.hc_balance: LAND_PRICE}))
        raise HTTPException(status_code=500, detail="Failed to purchase tile. Please try again.")

    return {"message": "Land purchased successfully!", "h3_index": h3_index, "new_balance": current_user.hc_balance - LAND_PRICE}


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
    await current_user.update(Inc({User.hc_balance: LAND_SELL_PRICE}))

    return {"message": "Land sold successfully!", "h3_index": h3_index, "new_balance": current_user.hc_balance + LAND_SELL_PRICE}