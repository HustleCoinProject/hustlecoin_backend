# core/game_logic.py
from datetime import datetime, timedelta
from typing import Dict, Any, Callable

# --- Imports for Logic ---
from data.models import User
from components.shop import SHOP_ITEMS_CONFIG # Important: Import the config
from core.config import settings

class EffectProcessor:
    """
    A registry and processor for all game effects.
    This makes it easy to add new effects by simply registering them.
    """
    
    # Registry of effect handlers
    _effect_handlers: Dict[str, Callable] = {}
    
    @classmethod
    def register_effect(cls, effect_name: str):
        """Decorator to register effect handlers"""
        def decorator(func):
            cls._effect_handlers[effect_name] = func
            return func
        return decorator
    
    @classmethod
    def apply_effects(cls, user: User, context: str, **kwargs) -> Dict[str, Any]:
        """
        Apply all active effects for a given context.
        
        Args:
            user: The User document object
            context: The context for which effects should be applied (e.g., 'task_reward', 'land_income', 'task_cooldown')
            **kwargs: Additional context-specific parameters
            
        Returns:
            Dictionary containing all modifiers to be applied
        """
        now = datetime.utcnow()
        modifiers = {
            'hc_multiplier': 1.0,
            'land_income_multiplier': 1.0,
            'task_speed_multiplier': 1.0,
            'cooldown_reduction_percentage': 0.0,
            'rank_point_multiplier': 1.0,
            'access_levels': [],
            'flat_bonuses': {}
        }
        
        # Process active inventory items
        for item in user.inventory:
            # Skip expired items
            if item.expires_at and item.expires_at <= now:
                continue
                
            # Get item configuration
            item_config = SHOP_ITEMS_CONFIG.get(item.item_id)
            if not item_config:
                continue
                
            # Get effect type and apply it
            effect = item_config["metadata"].get("effect")
            if effect in cls._effect_handlers:
                cls._effect_handlers[effect](modifiers, item_config, item, context, **kwargs)
        
        return modifiers


# Register all effect handlers
@EffectProcessor.register_effect("hc_multiplier")
def apply_hc_multiplier(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Multiplies HC rewards from tasks and tapping"""
    if context in ['task_reward', 'tapping_reward']:
        multiplier = item_config["metadata"].get("value", 1.0)
        modifiers['hc_multiplier'] *= multiplier

@EffectProcessor.register_effect("land_income_multiplier")
def apply_land_income_multiplier(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Multiplies passive land income"""
    if context == 'land_income':
        multiplier = item_config["metadata"].get("value", 1.0)
        modifiers['land_income_multiplier'] *= multiplier

@EffectProcessor.register_effect("task_speed_multiplier")
def apply_task_speed_multiplier(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Reduces task completion time (affects cooldowns)"""
    if context == 'task_cooldown':
        speed_multiplier = item_config["metadata"].get("value", 1.0)
        # Speed multiplier reduces the cooldown time (2x speed = 0.5x cooldown)
        modifiers['task_speed_multiplier'] *= speed_multiplier

@EffectProcessor.register_effect("cooldown_reduction_percentage")
def apply_cooldown_reduction(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Reduces task cooldowns by a percentage"""
    if context == 'task_cooldown':
        reduction_percentage = item_config["metadata"].get("value", 0)
        # Stack cooldown reductions additively (capped at 95% reduction)
        modifiers['cooldown_reduction_percentage'] = min(95.0, 
            modifiers['cooldown_reduction_percentage'] + reduction_percentage)

@EffectProcessor.register_effect("access_level")
def apply_access_level(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Grants access levels for features"""
    access_level = item_config["metadata"].get("access_level")
    if access_level and access_level not in modifiers['access_levels']:
        modifiers['access_levels'].append(access_level)

@EffectProcessor.register_effect("rank_point_multiplier")
def apply_rank_point_multiplier(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    """Multiplies rank point gains"""
    if context == 'rank_point_reward':
        multiplier = item_config["metadata"].get("value", 1.0)
        modifiers['rank_point_multiplier'] *= multiplier


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
        modifiers = EffectProcessor.apply_effects(user, 'task_reward', base_reward=base_reward)
        
        # Apply HC multiplier
        modified_reward = float(base_reward) * modifiers['hc_multiplier']
        
        # Apply flat bonuses if any
        for bonus_type, bonus_value in modifiers['flat_bonuses'].items():
            if bonus_type == 'hc_flat_bonus':
                modified_reward += bonus_value
        
        # Apply the user's level multiplier
        # New Formula: 1 + (Level - 1) * 0.25
        # Level 1: 1.0x
        # Level 2: 1.25x
        # Level 5: 2.0x (Previously 5.0x)
        level_multiplier = 1 + (user.level - 1) * 0.25
        final_reward = modified_reward * level_multiplier

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
        modifiers = EffectProcessor.apply_effects(user, 'land_income', time_diff_seconds=time_diff_seconds)
        
        base_income = time_diff_seconds * settings.LAND_INCOME_PER_SECOND
        final_income = base_income * modifiers['land_income_multiplier']
        
        return round(final_income)
    
    @staticmethod
    async def calculate_task_cooldown(user: User, base_cooldown_seconds: int) -> int:
        """
        Calculates the actual cooldown for a task after applying speed boosters
        and cooldown reduction effects.
        
        Args:
            user: The User document object.
            base_cooldown_seconds: The base cooldown time in seconds.
            
        Returns:
            The final, calculated cooldown time in seconds.
        """
        if base_cooldown_seconds <= 0:
            return 0
            
        modifiers = EffectProcessor.apply_effects(user, 'task_cooldown', base_cooldown_seconds=base_cooldown_seconds)
        
        # Apply speed multiplier (2x speed = 0.5x cooldown time)
        speed_adjusted_cooldown = base_cooldown_seconds / modifiers['task_speed_multiplier']
        
        # Apply cooldown reduction percentage
        reduction_factor = (100.0 - modifiers['cooldown_reduction_percentage']) / 100.0
        final_cooldown = speed_adjusted_cooldown * reduction_factor
        
        # Ensure minimum cooldown of 1 second for non-zero cooldowns
        return max(1, round(final_cooldown))
    
    @staticmethod
    async def has_access_level(user: User, required_level: str) -> bool:
        """
        Checks if the user has the required access level.
        
        Args:
            user: The User document object.
            required_level: The access level to check for ('bronze', 'silver', 'gold', 'platinum', 'permanent').
            
        Returns:
            True if the user has the required access level, False otherwise.
        """
        modifiers = EffectProcessor.apply_effects(user, 'access_check')
        
        # Define access level hierarchy
        access_hierarchy = {
            'bronze': 1,
            'silver': 2, 
            'gold': 3,
            'platinum': 4,
            'permanent': 5
        }
        
        required_level_value = access_hierarchy.get(required_level, 0)
        
        # Check if user has any access level that meets or exceeds the requirement
        for access_level in modifiers['access_levels']:
            user_level_value = access_hierarchy.get(access_level, 0)
            if user_level_value >= required_level_value:
                return True
                
        return False
    
    @staticmethod
    async def get_active_effects_summary(user: User) -> Dict[str, Any]:
        """
        Returns a summary of all currently active effects for the user.
        Useful for displaying active boosters in the UI.
        
        Args:
            user: The User document object.
            
        Returns:
            Dictionary containing active effects and their remaining durations.
        """
        now = datetime.utcnow()
        active_effects = []
        
        for item in user.inventory:
            # Skip expired items
            if item.expires_at and item.expires_at <= now:
                continue
                
            # Get item configuration
            item_config = SHOP_ITEMS_CONFIG.get(item.item_id)
            if not item_config:
                continue
                
            effect_info = {
                'item_id': item.item_id,
                'item_name': item_config.get('name', 'Unknown'),
                'effect_type': item_config["metadata"].get("effect"),
                'effect_value': item_config["metadata"].get("value"),
                'expires_at': item.expires_at.isoformat() if item.expires_at else None,
                'time_remaining_seconds': (
                    (item.expires_at - now).total_seconds() 
                    if item.expires_at else None
                )
            }
            active_effects.append(effect_info)
        
        return {
            'active_effects': active_effects,
            'total_active_effects': len(active_effects)
        }
    
    @staticmethod
    async def calculate_rank_point_reward(user: User, base_rank_points: int) -> int:
        """
        Calculates the final rank points earned after applying all active
        boosters and the user's level multiplier.
        
        Rank points represent user activity and importance in the game.
        They increase based on:
        - Task completion (base points based on task difficulty)
        - Daily check-ins and streaks
        - Land purchases and management
        - Tapping activity
        - Quiz participation
        - Overall game engagement
        
        Args:
            user: The User document object.
            base_rank_points: The base rank points for the completed action.
            
        Returns:
            The final, calculated rank points as an integer.
        """
        modifiers = EffectProcessor.apply_effects(user, 'rank_point_reward', base_rank_points=base_rank_points)
        
        # Apply rank point multiplier
        modified_points = float(base_rank_points) * modifiers['rank_point_multiplier']
        
        # Apply flat bonuses if any
        for bonus_type, bonus_value in modifiers['flat_bonuses'].items():
            if bonus_type == 'rank_points_flat_bonus':
                modified_points += bonus_value
        
        # Apply a smaller level multiplier for rank points (to prevent extreme scaling)
        level_multiplier = 1 + (user.level - 1) * 0.05  # 5% increase per level
        final_points = modified_points * level_multiplier

        return round(final_points)

    @staticmethod
    async def get_event_point_increments(user: User, points: int) -> Dict[str, int]:
        """
        Returns a dictionary of event point updates for all active events the user has joined.
        Used for MongoDB $inc updates.
        
        Args:
            user: The User document.
            points: The number of rank points earned.
            
        Returns:
            Dict mapping "events_points.{event_id}" to points increment.
        """
        updates = {}
        # Avoid circular import
        from components.events import get_event_cycle_times
        
        now = datetime.utcnow()
        
        for event_id, joined_at in user.joined_events.items():
            try:
                # Check if event is currently active (user joined current cycle)
                start, end = get_event_cycle_times(event_id)
                
                # We only award points if the current time is within the cycle
                # And importantly, if the user joined BEFORE the current time (which is always true if in joined_events)
                # But we should also check if the join time is within this CURRENT cycle or a previous one.
                # If joined in previous cycle, they need to rejoin (logic depends on if we clear joined_events)
                # PLAN: We will clear joined_events on reset. So if they are in there, they are in THIS cycle.
                
                if start <= now < end:
                     updates[f"events_points.{event_id}"] = points
            except Exception:
                continue
                
        return updates