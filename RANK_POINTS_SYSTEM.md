# Rank Points System Documentation

## Overview

The HustleCoin backend now includes a **Rank Points** system to better represent user activity, engagement, and importance in the game. Unlike HustleCoin (HC) balance which decreases when users make purchases, Rank Points only increase and reflect the user's overall "hustle" and activity level.

## Key Features

### 1. **Rank Points vs HustleCoin Balance**
- **HustleCoin (HC)**: Currency that can be spent on shop items, land, etc.
- **Rank Points**: Activity/achievement points that never decrease and reflect user engagement
- **Leaderboard**: Now ranks users by Rank Points instead of HC balance

### 2. **How Users Earn Rank Points**

#### **Task Completion** (components/tasks.py)
- **Daily Check-in**: 10 base points + streak bonus (2 points per day, max 7 days)
- **Watch Ad**: 5 points per completion
- **Daily Tap**: 8 points per completion  
- **Quiz Game**: 15 points for correct answers, 0 for incorrect

#### **Tapping System** (components/tapping.py)
- **Tapping**: 1 rank point per 5 taps (minimum 1 point per tap session)

#### **Land System** (components/land.py)
- **Land Purchase**: 25 rank points per land tile purchased

#### **Power Prestige Booster** (components/shop.py)
- **Active Effect**: Increases rank point gains by 50% when active
- **Works with**: All rank point earning activities

### 3. **Shop Item: Power Prestige**
- **Name**: Power Prestige
- **Price**: 200 HC
- **Duration**: 24 hours (1 day)
- **Effect**: `rank_point_multiplier` with 1.5x multiplier
- **Description**: "Increases Rank Point gains by 50% to help you climb the leaderboards."

### 4. **Bundle: Combo Boost Pack**
- **Name**: Combo Boost Pack  
- **Price**: 300 HC (saves 60 HC compared to buying individually)
- **Contains**: Speed Hustle + Double Coins + Power Prestige
- **Type**: BUNDLE - automatically adds all contained items to inventory

## API Changes

### **User Model Updates**
```json
{
  "id": "...",
  "username": "player123",
  "email": "user@example.com", 
  "hc_balance": 1500,
  "rank_points": 425,  // NEW FIELD
  "level": 3,
  // ... other fields
}
```

### **Leaderboard Endpoint** (`GET /api/leaderboard`)
**Response Updated:**
```json
[
  {
    "username": "topplayer",
    "rank_points": 1250,     // Now primary ranking field
    "level": 5,
    "hc_balance": 800        // Still included for reference
  }
]
```

### **Task Completion** (`POST /api/tasks/complete`)
**Response Updated:**
```json
{
  "message": "Task 'daily_check_in' completed successfully!",
  "new_balance": 1550,
  "new_rank_points": 440,           // NEW
  "rank_points_earned": 15,         // NEW  
  "cooldown_expires_at": "2025-11-30T12:00:00Z"
}
```

### **Task Info** (`GET /api/tasks/all`, `GET /api/tasks/status`) 
**Response Updated:**
```json
[
  {
    "task_id": "daily_check_in",
    "description": "Daily Check-In & Streak Bonus",
    "reward": 50,
    "rank_points": 10,        // NEW
    "type": "INSTANT",
    "cooldown_seconds": 79200,
    "is_available": true
  }
]
```

### **Tapping System** (`POST /api/tapping/tap`)
**Response Updated:**
```json
{
  "success": true,
  "message": "Successfully processed 20 taps! Earned 25 HC and 4 rank points.",
  "hc_earned": 25,
  "rank_points_earned": 4,          // NEW
  "new_balance": 1575,
  "new_rank_points": 444,           // NEW
  "daily_earnings": 120,
  "daily_limit": 200,
  "remaining_taps": 80
}
```

### **Land Purchase** (`POST /api/land/buy/{h3_index}`)
**Response Updated:**
```json
{
  "message": "Land purchased successfully! Earned 25 rank points.",
  "h3_index": "881f1d4a43fffff",
  "new_balance": 1075,
  "rank_points_earned": 25,         // NEW
  "new_rank_points": 469            // NEW
}
```

## Game Logic Integration

### **Rank Points Calculation**
```python
# Base rank points are calculated with:
final_rank_points = await GameLogic.calculate_rank_point_reward(
    user=current_user,
    base_rank_points=base_amount
)
```

### **Level Multiplier**
- Rank points get a smaller level multiplier than HC
- Formula: `level_multiplier = 1 + (user.level - 1) * 0.1`  
- Example: Level 5 user gets 1.4x multiplier (40% bonus)

### **Power Prestige Effect**
- When active, multiplies all rank point gains by 1.5x
- Stacks with level multiplier: `base_points * level_multiplier * 1.5`
- Applied to: tasks, tapping, land purchases, and any future activities

## Database Migration

### **Required Change**
Add `rank_points: int = 0` field to User model in `data/models/models.py`

### **Existing Users**
- All existing users will have `rank_points: 0` by default
- No data migration needed - they'll start earning points from their next activities

## Frontend Integration

### **Leaderboard Updates**
- Display rank points as primary ranking metric
- Show HC balance as secondary information
- Update sorting to use `rank_points` field

### **User Profile/Dashboard**
- Show both HC balance and rank points
- Display rank points prominently as "achievement/status" metric
- Show rank points earned in activity notifications

### **Task/Activity Rewards**
- Update reward displays to show both HC and rank points
- Example: "Earned 50 HC + 10 Rank Points!"

### **Shop Integration**
- Highlight Power Prestige as rank point booster
- Show Combo Boost Pack savings and contents clearly

## Benefits of This System

1. **Persistent Achievement**: Rank points never decrease, encouraging long-term play
2. **Activity Tracking**: Better represents user engagement than HC balance  
3. **Competitive Rankings**: Fairer leaderboards not affected by spending patterns
4. **Monetization**: Power Prestige provides incentive to purchase boosters
5. **User Retention**: Achievement-based progression alongside economic gameplay

## Future Expansion

The rank points system can be extended to include:
- Seasonal competitions and tournaments
- Achievement badges and titles
- VIP tier unlocks based on rank points
- Special events with rank point bonuses
- Social features (friend challenges, etc.)