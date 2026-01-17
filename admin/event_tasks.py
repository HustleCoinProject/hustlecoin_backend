# admin/event_tasks.py
from datetime import datetime, timedelta
import logging
from beanie import PydanticObjectId
from data.models import User, SystemSettings
from components.events import EVENTS_CONFIG, get_event_cycle_times
from beanie.operators import Inc, Set, Unset

logger = logging.getLogger(__name__)

async def check_event_resets():
    """
    Checks all defined events to see if their current cycle has ended.
    If ended, distributes rewards to winners and resets user progress for that event.
    Runs periodically (e.g., hourly).
    """
    logger.info("[EVENTS] Checking for event resets...")
    
    current_time = datetime.utcnow()
    
    for event_id, config in EVENTS_CONFIG.items():
        try:
            # Get current cycle times
            start_time, end_time = get_event_cycle_times(event_id)
            
            # Key to track the last processed cycle for this event
            # We want to process the cycle that JUST ended.
            # Example: current cycle ends at T1. Current time is T1 + 10min.
            # We check if we processed the cycle ending at T1.
            
            # Logic: valid cycle start times are anchor points.
            # We want to ensure the "previous" cycle has been processed.
            cycle_duration = timedelta(days=config["duration_days"])
            previous_cycle_start = start_time - cycle_duration
            previous_cycle_end = start_time
            
            # Unique key for this specific cycle reset
            # e.g., "event_1d_reset_2024-01-15T00:00:00"
            reset_key = f"{event_id}_reset_{previous_cycle_end.isoformat()}"
            
            # Check if we already processed this reset
            lock_doc = await SystemSettings.find_one({"setting_key": reset_key})
            if lock_doc:
                continue # Already processed
                
            # If we haven't processed it, check if it's time (current time >= previous cycle end)
            # This should always be true if we are in the "next" cycle
            if current_time >= previous_cycle_end:
                logger.info(f"[EVENTS] Processing reset for {event_id} (Cycle ended: {previous_cycle_end})")
                await _process_event_reset(event_id, previous_cycle_end, reset_key)
                
        except Exception as e:
            logger.error(f"[EVENTS] Error checking reset for {event_id}: {e}", exc_info=True)


async def _process_event_reset(event_id: str, cycle_end_date: datetime, reset_key: str):
    """
    Distributes rewards and resets data for a specific event cycle.
    """
    # 1. Acquire Lock (create the setting document)
    try:
        await SystemSettings(
            setting_key=reset_key,
            is_locked=True,
            locked_at=datetime.utcnow(),
            metadata={"status": "processing"}
        ).create()
    except Exception:
        # Duplicate key error means another instance picked it up
        logger.info(f"[EVENTS] Reset for {event_id} already in progress by another instance.")
        return

    try:
        config = EVENTS_CONFIG[event_id]
        
        # 2. Find Winners (Top 3) and Count Total Participants
        # We look for users who have points for this event > 0
        winners = await User.find(
            {f"events_points.{event_id}": {"$gt": 0}}
        ).sort(
            f"-events_points.{event_id}"
        ).limit(3).to_list()
        
        # Count total participants (all users who joined this event)
        total_participants = await User.find(
            {f"joined_events.{event_id}": {"$exists": True}}
        ).count()
        
        # Calculate dynamic reward pool: 1/3 of total entry fees
        entry_fee = config["entry_fee"]
        total_pool = (total_participants * entry_fee) // 3  # Integer division
        
        # Distribution percentages for top 3: 50%, 30%, 20%
        distribution = {1: 0.50, 2: 0.30, 3: 0.20}
        
        rewards_log = []
        
        # 3. Distribute Rewards from Pool
        for rank, user in enumerate(winners, start=1):
            if total_pool > 0:
                reward_amount = int(total_pool * distribution[rank])
            else:
                reward_amount = 0
            
            if reward_amount > 0:
                await user.update(Inc({User.hc_balance: reward_amount, User.hc_earned_in_level: reward_amount}))
                rewards_log.append(f"Rank {rank}: {user.username} (+ {reward_amount} HC)")
                logger.info(f"[EVENTS] Rewarded {user.username} {reward_amount} HC for {event_id} Rank {rank}")
        
        logger.info(f"[EVENTS] {event_id} - Participants: {total_participants}, Pool: {total_pool} HC (1/3 of {total_participants * entry_fee} HC), 2/3 burned")

        # 4. Reset Event Data for ALL Users
        # We remove the joined status and the points for this event
        # Logic: If a user hasn't joined the NEW cycle yet, clear their data.
        # But wait, if we clear 'joined_events', they have to rejoin. This is desired as they need to pay fee again.
        
        logger.info(f"[EVENTS] Resetting participants for {event_id}...")
        
        # Unset the specific event key from joined_events and events_points maps
        # MongoDB $unset requires dot notation for nested fields
        await User.find(
            {f"joined_events.{event_id}": {"$exists": True}}
        ).update(
            Unset({
                f"joined_events.{event_id}": "",
                f"events_points.{event_id}": ""
            })
        )
        
        # 5. Mark as Completed
        await SystemSettings.find_one({"setting_key": reset_key}).update(
            Set({
                "is_locked": False, 
                "last_executed_at": datetime.utcnow(),
                "metadata": {"status": "completed", "winners": rewards_log}
            })
        )
        
        logger.info(f"[EVENTS] Completed reset for {event_id}. Winners: {rewards_log}")
        
    except Exception as e:
        logger.error(f"[EVENTS] Failed during reset processing for {event_id}: {e}", exc_info=True)
        # Attempt to release lock or mark as failed so it can be retried or investigated
        await SystemSettings.find_one({"setting_key": reset_key}).update(
             Set({"metadata.status": "failed", "metadata.error": str(e)})
        )
