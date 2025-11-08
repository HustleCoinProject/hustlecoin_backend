# Game Logic System Documentation

## Overview

The HustleCoin backend now features a completely redesigned, scalable game logic system that makes it easy to add, modify, or remove item effects without touching multiple files.

## Key Features

### 🔧 **Scalable Architecture**
- **Effect Registry**: All effects are registered in a central registry
- **Modular Design**: Adding new effects requires only registering a new handler function
- **Context-Aware**: Effects can be applied differently based on context (task rewards, land income, cooldowns, etc.)

### ⚡ **Currently Implemented Effects**

| Effect Type | Items | Description |
|-------------|-------|-------------|
| `hc_multiplier` | Double Coins | Multiplies HC rewards from tasks and tapping |
| `land_income_multiplier` | Land Multiplier | Boosts passive land income |
| `task_speed_multiplier` | Speed Hustle | Reduces task completion time (affects cooldowns) |
| `cooldown_reduction_percentage` | Hustler Brain | Reduces task cooldowns by percentage |
| `access_level` | Bronze Key | Grants access to features based on tier |

### 🛡️ **Commented Out Items**
These items are temporarily disabled in the shop config:
- `power_prestige` (Rank Point multiplier - not yet implemented)
- `safe_lock_recharger` (Community Safe feature - not yet implemented) 
- `combo_boost_pack` (Bundle containing disabled items)
- `silver_key`, `gold_key`, `platinum_key`, `permanent_key` (Advanced access tiers)

## How It Works

### Effect Processing Flow
1. **User Action** (task completion, land collection, etc.)
2. **Context Determination** (task_reward, land_income, task_cooldown, etc.)
3. **Inventory Scan** (find all active, non-expired items)
4. **Effect Application** (apply all relevant effects for the context)
5. **Final Calculation** (combine all modifiers and return result)

### Example: Task Reward Calculation
```python
# Base reward: 100 HC
# User level: 2
# Active effects: Double Coins (2x multiplier)

final_reward = base_reward * hc_multiplier * user_level
# 100 * 2.0 * 2 = 400 HC
```

## API Endpoints

### Enhanced Endpoints
- `GET /api/users/inventory` - Now returns complete inventory data with item details, effects, and status
- All task completions now use dynamic cooldown calculation
- Land income calculations include booster effects
- Tapping rewards include booster effects

### Inventory Response Structure
```json
{
  "item_id": "double_coins",
  "quantity": 1,
  "purchased_at": "2025-11-08T10:30:00Z",
  "expires_at": "2025-11-08T11:30:00Z",
  "name": "Double Coins",
  "description": "Doubles the HustleCoin (HC) you earn from tasks.",
  "item_type": "BOOSTER",
  "time_remaining_seconds": 3600
}
```

## Adding New Effects

### Step 1: Add Item to Shop Config
```python
"new_booster": {
    "item_id": "new_booster",
    "name": "New Booster", 
    "price": 150,
    "description": "Does something cool",
    "item_type": "BOOSTER",
    "metadata": {"effect": "new_effect_type", "value": 1.5, "duration_seconds": 3600}
}
```

### Step 2: Register Effect Handler
```python
@EffectProcessor.register_effect("new_effect_type")
def apply_new_effect(modifiers: Dict[str, Any], item_config: Dict[str, Any], item, context: str, **kwargs):
    if context == 'relevant_context':
        value = item_config["metadata"].get("value", 1.0)
        # Apply the effect to modifiers
        modifiers['some_modifier'] *= value
```

### Step 3: Use in Game Logic
```python
@staticmethod
async def calculate_something(user: User, base_value: int) -> int:
    modifiers = EffectProcessor.apply_effects(user, 'relevant_context')
    return round(base_value * modifiers['some_modifier'])
```

## Testing

Run the test script to verify all effects are working:
```bash
python _test/test_game_logic.py
```

## Migration Notes

### What Changed
- ✅ All existing functionality preserved
- ✅ New effects added for speed, cooldown reduction, and access levels
- ✅ Commented out non-functional items in shop
- ✅ Enhanced task cooldown calculation with boosters
- ✅ Compact inventory endpoint with essential display data (active items only)

### What's Next
Future features can be easily added by:
1. Uncommenting items in shop config
2. Implementing their effect handlers
3. Adding any necessary game logic methods

This system is designed to scale effortlessly as the game grows!
