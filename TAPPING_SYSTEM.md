# Tapping System Implementation

## Overview

The tapping system has been separated from the task system to improve performance, reduce spam, and provide better user experience. The new system implements daily limits and batch processing.

## Key Changes

### 1. New Component: `components/tapping.py`

- **Endpoint**: `/api/tapping/` (separated from `/api/tasks/`)
- **Daily Limit**: 200 HC per user per day
- **Batch Processing**: Process 1-100 taps per request
- **Daily Reset**: Automatic reset at midnight UTC

### 2. Updated User Model (`components/users.py`)

Added new fields to track daily tap earnings:
```python
daily_tap_earnings: int = 0  # HC earned from taps today
last_tap_reset_date: date | None = None  # Last date when tap earnings were reset
```

### 3. Removed from Tasks System

- Removed `"quick_tap"` from `TASK_CONFIG` in `components/tasks.py`
- Removed quick_tap logic from task completion endpoint
- Updated task cooldown logic to be more robust

## API Endpoints

### GET `/api/tapping/status`

Get current tapping status for the authenticated user.

**Response:**
```json
{
  "daily_earnings": 50,
  "daily_limit": 200,
  "remaining_taps": 150,
  "can_tap": true,
  "next_reset_at": null
}
```

### POST `/api/tapping/tap`

Process a batch of taps and award HC based on daily limits.

**Request:**
```json
{
  "tap_count": 10
}
```

**Success Response:**
```json
{
  "success": true,
  "message": "Successfully processed 10 taps! Earned 10 HC.",
  "hc_earned": 10,
  "new_balance": 1010,
  "daily_earnings": 60,
  "daily_limit": 200,
  "remaining_taps": 140,
  "next_reset_at": null
}
```

**Daily Limit Reached Response (HTTP 429):**
```json
{
  "message": "Daily tap limit reached. Try again tomorrow!",
  "next_reset_at": "2025-11-08T00:00:00",
  "daily_earnings": 200,
  "daily_limit": 200
}
```

## Features

### 1. Daily Limits
- Each user can earn maximum 200 HC from tapping per day
- Limits reset automatically at midnight UTC
- Clear feedback when limits are reached

### 2. Batch Processing
- Process 1-100 taps per request (configurable via Pydantic validation)
- Reduces server load compared to individual tap requests
- More efficient database operations

### 3. Game Logic Integration
- Still applies level multipliers and booster effects
- Uses existing `GameLogic.calculate_task_reward()` system
- Maintains game balance while improving performance

### 4. Spam Protection
- Daily limits prevent abuse
- Batch processing reduces request frequency
- Proper error handling with meaningful messages

### 5. Automatic Reset System
- Daily earnings reset at midnight UTC
- Tracks last reset date to handle edge cases
- Configurable reset hour (currently set to 0 = midnight)

## Configuration

Key configuration constants in `components/tapping.py`:

```python
DAILY_TAP_LIMIT = 200  # Maximum HC that can be earned per day from tapping
TAP_RESET_HOUR = 0     # Hour when daily limit resets (24-hour format, UTC)
```

## Benefits

1. **Performance**: Reduced server load through batch processing
2. **User Experience**: Clear feedback on limits and remaining taps
3. **Anti-Spam**: Daily limits prevent system abuse
4. **Maintainability**: Separated concerns from task system
5. **Scalability**: More efficient database operations
6. **Game Balance**: Maintains existing bonus systems

## Migration Notes

- Frontend should update to use new `/api/tapping/` endpoints instead of `quick_tap` task
- Batch multiple taps into single requests for better performance
- Handle daily limit responses appropriately
- The old `quick_tap` task is no longer available

## Testing

Use the provided test script `_test/tapping_demo.py` to see examples of the new API responses and understand the system behavior.
