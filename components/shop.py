
# TODO: Delete items in inventory if expired/used-up



# components/shop.py
from datetime import datetime, timedelta
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from beanie import Document, PydanticObjectId
from beanie.operators import Inc, Push

from core.security import get_current_user
from components.users import User, InventoryItem

router = APIRouter(prefix="/api/shop", tags=["Shop & Inventory"])

# --- Beanie Document Model for Shop Items ---
class ShopItem(Document):
    """Defines an item available for purchase in the shop."""
    item_id: str = Field(..., unique=True) # A unique string identifier, e.g., "double_hc_booster_1hr"
    name: str
    description: str
    price: int # Cost in HustleCoin (HC)
    
    # Type of item determines its effect
    item_type: Literal["BOOSTER", "DECORATION", "SPECIAL"] = "SPECIAL"
    
    # Effect-specific metadata
    # For a BOOSTER, this could define the multiplier and duration
    # For a DECORATION, this could be an image URL
    metadata: dict = Field(default_factory=dict)
    
    is_active: bool = True # To easily enable/disable items in the shop

    class Settings:
        name = "shop_items"


# --- DTOs (Data Transfer Objects) ---
class ShopItemOut(BaseModel):
    item_id: str
    name: str
    description: str
    price: int
    item_type: str
    metadata: dict

class PurchaseRequest(BaseModel):
    item_id: str
    quantity: int = 1

# --- Endpoints ---


@router.get("/items", response_model=List[ShopItemOut])
async def list_shop_items():
    """Lists all active items available for purchase."""
    items = await ShopItem.find(ShopItem.is_active == True).to_list()
    return items



@router.get("/user/inventory", response_model=List[InventoryItem])
async def get_user_inventory(current_user: User = Depends(get_current_user)):
    """Views the current user's inventory of purchased items."""
    return current_user.inventory



@router.post("/purchase")
async def purchase_item(
    purchase_data: PurchaseRequest,
    current_user: User = Depends(get_current_user)
):
    """Purchases an item from the shop."""
    item_to_buy = await ShopItem.find_one(ShopItem.item_id == purchase_data.item_id, ShopItem.is_active == True)
    
    if not item_to_buy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found or unavailable.")
        
    total_cost = item_to_buy.price * purchase_data.quantity
    
    if current_user.hc_balance < total_cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient HustleCoin.")

    # --- Create the inventory item entry ---
    new_inventory_item = InventoryItem(
        item_id=item_to_buy.item_id,
        quantity=purchase_data.quantity
    )
    
    # Handle timed boosters
    if item_to_buy.item_type == "BOOSTER" and "duration_seconds" in item_to_buy.metadata:
        duration = timedelta(seconds=item_to_buy.metadata["duration_seconds"])
        new_inventory_item.expires_at = datetime.utcnow() + duration
        
    # --- Perform atomic update ---
    await current_user.update(
        Inc({User.hc_balance: -total_cost}),
        Push({User.inventory: new_inventory_item.model_dump()}) # Use model_dump for sub-documents
    )
    
    return {
        "message": f"Successfully purchased {purchase_data.quantity} x {item_to_buy.name}!",
        "new_balance": current_user.hc_balance - total_cost
    }



@router.post("/dev/seed-items", include_in_schema=False)
async def seed_shop_items():
    """Endpoint to add sample items to the DB. Not for production."""
    await ShopItem.delete_all()
    items_to_seed = [
        ShopItem(
            item_id="double_hc_booster_1hr",
            name="Double HC Booster (1 Hour)",
            description="Earn 2x HustleCoin from all tasks for one hour.",
            price=1000,
            item_type="BOOSTER",
            metadata={"multiplier": 2, "duration_seconds": 3600}
        ),
        ShopItem(
            item_id="presidential_desk_decoration",
            name="Presidential Desk",
            description="A purely cosmetic item to show off your status.",
            price=50000,
            item_type="DECORATION",
            metadata={"image_url": "https/example.com/desk.png"}
        ),
        ShopItem(
            item_id="one_time_hc_pack",
            name="HC Starter Pack",
            description="A special one-time purchase item (logic not implemented yet).",
            price=200,
            item_type="SPECIAL"
        ),
    ]
    await ShopItem.insert_many(items_to_seed)
    return {"message": f"{len(items_to_seed)} shop items seeded successfully."}