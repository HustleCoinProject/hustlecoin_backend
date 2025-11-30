# components/shop.py
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from core.rate_limiter_slowapi import api_limiter
from pydantic import BaseModel, Field
from beanie.operators import Inc, Push, And

from data.models import User, InventoryItem
from core.security import get_current_user
from core.translations import translate_text, translate_dict_values




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
    # "safe_lock_recharger": {
    #     "item_id": "safe_lock_recharger", "name": "Safe Lock Recharger", "price": 80,
    #     "description": "Instantly adds 5% to the community Safe Luck Fund.",
    #     "item_type": "SPECIAL",
    #     "metadata": {"effect": "add_to_safe_luck_fund", "value_percentage": 5} # Instant
    # },
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
        "metadata": {"effect": "access_level", "access_level": "bronze", "duration_seconds": 259200} # 3 days
    },
    # "silver_key": {
    #     "item_id": "silver_key", "name": "Silver Key", "price": 250,
    #     "description": "Unlocks rare spells, all lands, and special events.",
    #     "item_type": "ACCESS_KEY",
    #     "metadata": {"access_level": "silver", "duration_seconds": 604800} # 7 days
    # },
    # "gold_key": {
    #     "item_id": "gold_key", "name": "Gold Key", "price": 500,
    #     "description": "Unlocks VIP tasks and ranking boards.",
    #     "item_type": "ACCESS_KEY",
    #     "metadata": {"access_level": "gold", "duration_seconds": 1296000} # 15 days
    # },
    # "platinum_key": {
    #     "item_id": "platinum_key", "name": "Platinum Key", "price": 900,
    #     "description": "Grants full access to all features and VIP bonuses.",
    #     "item_type": "ACCESS_KEY",
    #     "metadata": {"access_level": "platinum", "duration_seconds": 2592000} # 30 days
    # },
    # "permanent_key": {
    #     "item_id": "permanent_key", "name": "Permanent Key", "price": 10000,
    #     "description": "Grants lifetime full access and an elite title.",
    #     "item_type": "ACCESS_KEY",
    #     "metadata": {"access_level": "permanent", "title": "Elite"} # Forever
    # }
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
async def list_shop_items(current_user: User = Depends(get_current_user)):
    """Lists all active items available for purchase from the static config, translated to user's language."""
    user_language = current_user.language
    translated_items = []
    
    for item in SHOP_ITEMS_CONFIG.values():
        # Create a copy of the item to avoid modifying the original
        translated_item = item.copy()
        
        # Translate name and description
        translated_item["name"] = translate_text(item["name"], user_language)
        translated_item["description"] = translate_text(item["description"], user_language)
        
        translated_items.append(translated_item)
    
    return translated_items




@router.post("/purchase")
@api_limiter.limit("10/minute")
async def purchase_item(
    request: Request,
    purchase_data: PurchaseRequest,
    current_user: User = Depends(get_current_user)
):
    item_data = SHOP_ITEMS_CONFIG.get(purchase_data.item_id)
    
    if not item_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    
    item_to_buy = ShopItemOut(**item_data)
    translated_item_name = translate_text(item_data["name"], current_user.language)
    total_cost = item_to_buy.price * purchase_data.quantity
    
    # Check balance first, but will do atomic check during update
    if current_user.hc_balance < total_cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin.")

    # --- Handle special instant-effect items ---
    if item_to_buy.item_type == "SPECIAL":
        # Atomic deduction for special items with balance verification
        from beanie.operators import And
        update_result = await User.find_one(
            And(User.id == current_user.id, User.hc_balance >= total_cost)
        ).update(Inc({User.hc_balance: -total_cost}))
        
        if not update_result:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin or concurrent purchase detected.")
        return {
            "message": f"Successfully activated {translated_item_name}!",
            "new_balance": current_user.hc_balance - total_cost
        }
    
    # ### NEW ### --- Handle BUNDLE item type ---
    if item_to_buy.item_type == "BUNDLE":
        if purchase_data.quantity > 1:
            # To keep logic simple, we'll restrict bundle purchases to one at a time.
            raise HTTPException(status_code=400, detail="Can only purchase one bundle at a time.")
        
        bundle_items = item_to_buy.metadata.get("contains", [])
        inventory_additions = []
        for sub_item_id in bundle_items:
            sub_item_data = SHOP_ITEMS_CONFIG.get(sub_item_id)
            if not sub_item_data: continue # Skip if an item in bundle is misconfigured

            new_inventory_item = InventoryItem(item_id=sub_item_id, quantity=1)
            
            if "duration_seconds" in sub_item_data["metadata"]:
                duration = timedelta(seconds=sub_item_data["metadata"]["duration_seconds"])
                new_inventory_item.expires_at = datetime.utcnow() + duration
            
            inventory_additions.append(new_inventory_item.model_dump())
        
        # Atomically deduct cost and push all bundle items to inventory with balance check
        from beanie.operators import And
        update_result = await User.find_one(
            And(User.id == current_user.id, User.hc_balance >= total_cost)
        ).update(
            Inc({User.hc_balance: -total_cost}),
            Push({User.inventory: {"$each": inventory_additions}})
        )
        
        if not update_result:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin or concurrent purchase detected.")
        return {
            "message": f"Successfully purchased bundle: {translated_item_name}!",
            "new_balance": current_user.hc_balance - total_cost
        }

    # --- Standard Item Purchase ---
    new_inventory_item = InventoryItem(
        item_id=item_to_buy.item_id,
        quantity=purchase_data.quantity,
        purchased_at=datetime.utcnow()
    )
    
    if "duration_seconds" in item_to_buy.metadata:
        duration = timedelta(seconds=item_to_buy.metadata["duration_seconds"])
        new_inventory_item.expires_at = datetime.utcnow() + (duration * purchase_data.quantity)
        
    # Atomic purchase with balance verification
    from beanie.operators import And
    update_result = await User.find_one(
        And(User.id == current_user.id, User.hc_balance >= total_cost)
    ).update(
        Inc({User.hc_balance: -total_cost}),
        Push({User.inventory: new_inventory_item.model_dump()})
    )
    
    if not update_result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin or concurrent purchase detected.")
    
    return {
        "message": f"Successfully purchased {purchase_data.quantity} x {translated_item_name}!",
        "new_balance": current_user.hc_balance - total_cost
    }