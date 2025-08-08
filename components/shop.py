# components/shop.py
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from beanie.operators import Inc, Push

from core.security import get_current_user
from components.users import User, InventoryItem




# components/shop_config.py

"""
This file serves as the static configuration for all items available in the shop.
The shop's endpoints will read directly from this configuration instead of a database.
This makes managing shop items as simple as editing this file.

The dictionary key is the unique 'item_id', which is used for lookups.
"""

SHOP_ITEMS_CONFIG = {
    # --- Spells (Boosters) ---
    "speed_hustle": {
        "item_id": "speed_hustle", "name": "Speed Hustle", "price": 60,
        "description": "Completes all of your tasks 2x faster.",
        "item_type": "BOOSTER",
        "metadata": {"effect": "task_speed_multiplier", "value": 2, "duration_seconds": 7200} # 2 hours
    },
    "double_coins": {
        "item_id": "double_coins", "name": "Double Coins", "price": 100,
        "description": "Doubles the HustleCoin (HC) you earn from tasks.",
        "item_type": "BOOSTER",
        "metadata": {"effect": "hc_multiplier", "value": 2, "duration_seconds": 3600} # 1 hour
    },
    "power_prestige": {
        "item_id": "power_prestige", "name": "Power Prestige", "price": 200,
        "description": "Increases Rank Point gains by 50% to help you climb the leaderboards.",
        "item_type": "BOOSTER",
        "metadata": {"effect": "rank_point_multiplier", "value": 1.5, "duration_seconds": 86400} # 1 day
    },
    "hustler_brain": {
        "item_id": "hustler_brain", "name": "Hustler Brain", "price": 90,
        "description": "Reduces the cooldown on your tasks by 50%.",
        "item_type": "BOOSTER",
        "metadata": {"effect": "cooldown_reduction_percentage", "value": 50, "duration_seconds": 14400} # 4 hours
    },
    "land_multiplier": {
        "item_id": "land_multiplier", "name": "Land Multiplier", "price": 250,
        "description": "Boosts your passive land income by 100%.",
        "item_type": "BOOSTER",
        "metadata": {"effect": "land_income_multiplier", "value": 2, "duration_seconds": 259200} # 3 days
    },
    # --- Special Items ---
    "safe_lock_recharger": {
        "item_id": "safe_lock_recharger", "name": "Safe Lock Recharger", "price": 80,
        "description": "Instantly adds 5% to the community Safe Luck Fund.",
        "item_type": "SPECIAL",
        "metadata": {"effect": "add_to_safe_luck_fund", "value_percentage": 5} # Instant
    },
    # --- Bundles ---
    "combo_boost_pack": {
        "item_id": "combo_boost_pack", "name": "Combo Boost Pack", "price": 300,
        "description": "A high-value bundle containing Speed Hustle, Double Coins, and Power Prestige.",
        "item_type": "BUNDLE",
        "metadata": {"contains": ["speed_hustle", "double_coins", "power_prestige"]}
    },
    # --- Access Keys ---
    "bronze_key": {
        "item_id": "bronze_key", "name": "Bronze Key", "price": 100,
        "description": "Unlocks access to basic spells, land, and boosters.",
        "item_type": "ACCESS_KEY",
        "metadata": {"access_level": "bronze", "duration_seconds": 259200} # 3 days
    },
    "silver_key": {
        "item_id": "silver_key", "name": "Silver Key", "price": 250,
        "description": "Unlocks rare spells, all lands, and special events.",
        "item_type": "ACCESS_KEY",
        "metadata": {"access_level": "silver", "duration_seconds": 604800} # 7 days
    },
    "gold_key": {
        "item_id": "gold_key", "name": "Gold Key", "price": 500,
        "description": "Unlocks VIP tasks and ranking boards.",
        "item_type": "ACCESS_KEY",
        "metadata": {"access_level": "gold", "duration_seconds": 1296000} # 15 days
    },
    "platinum_key": {
        "item_id": "platinum_key", "name": "Platinum Key", "price": 900,
        "description": "Grants full access to all features and VIP bonuses.",
        "item_type": "ACCESS_KEY",
        "metadata": {"access_level": "platinum", "duration_seconds": 2592000} # 30 days
    },
    "permanent_key": {
        "item_id": "permanent_key", "name": "Permanent Key", "price": 10000,
        "description": "Grants lifetime full access and an elite title.",
        "item_type": "ACCESS_KEY",
        "metadata": {"access_level": "permanent", "title": "Elite"} # Forever
    }
}



router = APIRouter(prefix="/api/shop", tags=["Shop & Inventory"])

# --- DTOs (Data Transfer Objects) ---
# This model defines the structure of a shop item sent to the client.
# It matches the structure of the items in SHOP_ITEMS_CONFIG.
class ShopItemOut(BaseModel):
    item_id: str
    name: str
    description: str
    price: int
    item_type: str
    metadata: dict

class PurchaseRequest(BaseModel):
    item_id: str
    quantity: int = Field(default=1, gt=0)

# --- Endpoints ---


@router.get("/items", response_model=List[ShopItemOut])
async def list_shop_items():
    """Lists all active items available for purchase from the static config."""
    # We simply return all the items defined in our configuration dictionary.
    return list(SHOP_ITEMS_CONFIG.values())




@router.post("/purchase")
async def purchase_item(
    purchase_data: PurchaseRequest,
    current_user: User = Depends(get_current_user)
):
    """Purchases an item by validating against the static shop config."""
    # Look up the item in our config dictionary instead of the database.
    item_data = SHOP_ITEMS_CONFIG.get(purchase_data.item_id)
    
    if not item_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found or unavailable.")
    
    # Use the ShopItemOut model to easily access item properties
    item_to_buy = ShopItemOut(**item_data)
        
    total_cost = item_to_buy.price * purchase_data.quantity
    
    if current_user.hc_balance < total_cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin.")

    # --- Handle special instant-effect items that aren't added to inventory ---
    if item_to_buy.item_type == "SPECIAL" and item_to_buy.item_id == "safe_lock_recharger":
        # TODO: Implement the logic to apply this instant effect (e.g., update a global state).
        await current_user.update(Inc({User.hc_balance: -total_cost}))
        return {
            "message": f"Successfully activated {item_to_buy.name}!",
            "new_balance": current_user.hc_balance - total_cost
        }
    
    # --- TODO: Handle BUNDLE item type ---
    if item_to_buy.item_type == "BUNDLE":
        # Logic for bundles: fetch items from metadata and add them individually.
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Bundle purchases are not yet implemented.")

    # --- Create the inventory item entry for all other items ---
    new_inventory_item = InventoryItem(
        item_id=item_to_buy.item_id,
        quantity=purchase_data.quantity,
        purchased_at=datetime.utcnow()
    )
    
    # Handle timed items by checking for duration in metadata
    if "duration_seconds" in item_to_buy.metadata:
        duration = timedelta(seconds=item_to_buy.metadata["duration_seconds"])
        new_inventory_item.expires_at = datetime.utcnow() + duration
        
    # --- Perform atomic update to deduct cost and add item to user's DB document ---
    await current_user.update(
        Inc({User.hc_balance: -total_cost}),
        Push({User.inventory: new_inventory_item.model_dump()})
    )
    
    return {
        "message": f"Successfully purchased {purchase_data.quantity} x {item_to_buy.name}!",
        "new_balance": current_user.hc_balance - total_cost
    }
