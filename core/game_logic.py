# core/game_logic.py
from datetime import datetime
from pymongo import UpdateOne
from motor.motor_asyncio import AsyncIOMotorClient
from collections import defaultdict
from beanie import PydanticObjectId

# --- Imports for Logic ---
from components.users import User
from components.shop import SHOP_ITEMS_CONFIG # Important: Import the config
from core.config import settings

# NEW: The central logic applicator
class GameLogic:
    """
    A central class for applying all game logic modifiers like levels,
    boosters, spells, and other inventory effects.
    """
    @staticmethod
    async def calculate_task_reward(user: User, base_reward: int) -> int:
        """
        Calculates the final reward for a task after applying all active
        boosters and the user's level multiplier.

        Args:
            user: The User document object.
            base_reward: The base HC reward for the completed task.

        Returns:
            The final, calculated HC reward as an integer.
        """
        now = datetime.utcnow()
        current_reward = float(base_reward)
        hc_multiplier = 1.0

        # 1. Apply active boosters from inventory
        for item in user.inventory:
            # Skip expired items
            if item.expires_at and item.expires_at <= now:
                continue

            # Find the item's configuration
            item_config = SHOP_ITEMS_CONFIG.get(item.item_id)
            if not item_config:
                continue
            
            # Apply effect based on item metadata
            effect = item_config["metadata"].get("effect")
            if effect == "hc_multiplier":
                hc_multiplier *= item_config["metadata"].get("value", 1.0)
            # Add other future effects here (e.g., flat bonuses)
            # elif effect == "flat_hc_bonus":
            #     current_reward += item_config["metadata"].get("value", 0)

        # 2. Apply the consolidated multipliers
        modified_reward = current_reward * hc_multiplier

        # 3. Apply the user's level multiplier
        final_reward = modified_reward * user.level

        return round(final_reward)

    @staticmethod
    async def calculate_land_income(user: User, time_diff_seconds: float) -> int:
        """
        Calculates the passive income from land for a given duration,
        applying all relevant user boosters.

        Args:
            user: The User document object.
            time_diff_seconds: The number of seconds since the last payout.

        Returns:
            The final, calculated passive income as an integer.
        """
        now = datetime.utcnow()
        base_income = time_diff_seconds * settings.LAND_INCOME_PER_SECOND
        land_multiplier = 1.0

        # Apply active boosters from inventory
        for item in user.inventory:
            if item.expires_at and item.expires_at <= now:
                continue
            
            item_config = SHOP_ITEMS_CONFIG.get(item.item_id)
            if not item_config:
                continue
                
            effect = item_config["metadata"].get("effect")
            if effect == "land_income_multiplier":
                land_multiplier *= item_config["metadata"].get("value", 1.0)

        final_income = base_income * land_multiplier
        return round(final_income)





# --- The background task remains, but it will be refactored to use the GameLogic class ---

async def distribute_land_income_logic_stateful():
    """
    Calculates and distributes passive land income.
    Refactored to use the central GameLogic class.
    """
    print("Starting STATEFUL land income distribution process...")
    
    client = AsyncIOMotorClient(settings.MONGO_DETAILS)
    db = client.get_database("hustlecoin_db")
    land_collection = db.land_tiles
    user_collection = db.users

    # --- Fetch all users who own land to get their inventory and level ---
    land_owner_ids = await land_collection.distinct("owner_id")
    if not land_owner_ids:
        print("No land owners found. Process finished.")
        client.close()
        return {"message": "No land owners to process.", "updated_users": 0}

    # Create a map of {user_id: user_object} for efficient lookup
    users_cursor = User.find(User.id.in_(land_owner_ids))
    owner_map = {user.id: user async for user in users_cursor}

    payout_time = datetime.utcnow()
    income_per_user = defaultdict(float)
    processed_tile_ids = []

    cursor = land_collection.find({})
    async for tile_doc in cursor:
        tile_id = tile_doc["_id"]
        owner_id = tile_doc["owner_id"]
        last_payout = tile_doc["last_income_payout_at"]

        owner = owner_map.get(owner_id)
        if not owner:
            continue # Skip tiles with no active owner

        time_diff_seconds = (payout_time - last_payout).total_seconds()
        if time_diff_seconds <= 0:
            continue
            
        # --- HERE is the change: Call the GameLogic class ---
        earned_income = await GameLogic.calculate_land_income(
            user=owner,
            time_diff_seconds=time_diff_seconds
        )

        income_per_user[owner_id] += earned_income
        processed_tile_ids.append(tile_id)

    if not income_per_user:
        print("No income to distribute. Process finished.")
        client.close()
        return {"message": "No income to distribute.", "updated_users": 0}
        
    # --- Database Updates (this part remains the same) ---
    user_updates = [
        UpdateOne(
            {"_id": PydanticObjectId(user_id)},
            {"$inc": {"hc_balance": round(total_income)}}
        )
        for user_id, total_income in income_per_user.items()
    ]
    
    tile_update_result = await land_collection.update_many(
        {"_id": {"$in": processed_tile_ids}},
        {"$set": {"last_income_payout_at": payout_time}}
    )

    user_update_result = await user_collection.bulk_write(user_updates)

    client.close()
    
    print(f"Income distributed. {user_update_result.modified_count} users updated. {tile_update_result.modified_count} tiles updated.")
    return {
        "message": "Stateful income distribution complete.",
        "updated_users": user_update_result.modified_count,
        "processed_tiles": tile_update_result.modified_count
    }