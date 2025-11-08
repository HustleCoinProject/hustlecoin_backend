# core/game_logic.py
from datetime import datetime

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