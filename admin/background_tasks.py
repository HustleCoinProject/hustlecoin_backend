# admin/background_tasks.py
from typing import List, Dict
from datetime import datetime, timedelta
from beanie import PydanticObjectId
from data.models.models import Payout, User, SystemSettings, LeaderboardHistory
from .crud import bulk_process_payouts
import logging

logger = logging.getLogger(__name__)


async def process_payouts_background(payouts_to_process: List[Dict], admin_username: str):
    """Process payouts in background after CSV validation."""
    try:
        print(f"[BACKGROUND] Processing {len(payouts_to_process)} payouts for {admin_username}")
        
        # Re-validate payouts are still pending (prevents duplicates)
        valid_payouts = []
        for payout_data in payouts_to_process:
            try:
                payout = await Payout.get(PydanticObjectId(payout_data['payout_id']))
                if payout and payout.status == 'pending':
                    valid_payouts.append(payout_data)
            except Exception:
                pass  # Skip invalid payouts
        
        if valid_payouts:
            results = await bulk_process_payouts(valid_payouts, admin_username)
            print(f"[BACKGROUND] Completed: {results['processed']} processed, {results['failed']} failed")
        else:
            print(f"[BACKGROUND] No valid payouts remaining to process")
            
    except Exception as e:
        print(f"[BACKGROUND] Error: {str(e)}")


async def reset_all_rank_points():
    """
    Reset rank_points to 0 for all users. Runs weekly on Mondays.
    Uses MongoDB atomic locking to prevent concurrent execution from multiple instances.
    """
    lock_key = "rank_reset_lock"
    lock_acquired = False
    
    try:
        # Clean up stale locks (older than 10 minutes)
        stale_threshold = datetime.utcnow() - timedelta(minutes=10)
        await SystemSettings.find_one(
            {"setting_key": lock_key, "locked_at": {"$lt": stale_threshold}}
        ).update({"$set": {"is_locked": False, "locked_at": None}})
        
        # Try to acquire MongoDB lock atomically using findOneAndUpdate
        # This ensures only ONE instance can acquire the lock
        current_time = datetime.utcnow()
        result = await SystemSettings.find_one(
            {"setting_key": lock_key, "is_locked": False}
        ).update(
            {"$set": {"is_locked": True, "locked_at": current_time}},
            upsert=True
        )
        
        # Verify we acquired the lock by checking the document
        setting = await SystemSettings.find_one({"setting_key": lock_key})
        if not setting or not setting.is_locked:
            logger.info("[RANK RESET] Another instance is already executing rank reset")
            return
        
        # Verify the lock timestamp matches our acquisition time (within 2 seconds)
        if setting.locked_at and abs((current_time - setting.locked_at).total_seconds()) > 2:
            logger.info("[RANK RESET] Lock acquired by another instance, skipping")
            return
        
        lock_acquired = True
        logger.info("[RANK RESET] Acquired MongoDB lock successfully")
        
        # STEP 1: Reward top 3 users before resetting
        logger.info("[RANK RESET] Finding top 3 users to reward...")
        top_users = await User.find(
            User.rank_points > 0
        ).sort(-User.rank_points).limit(3).to_list()
        
        if top_users:
            # Reward: Half of rank_points as HC (integer division)
            for rank, user in enumerate(top_users, start=1):
                if user.rank_points > 0:
                    reward_hc = user.rank_points // 2  # Integer division for half
                    
                    # Award HC to the user
                    user.hc_balance += reward_hc
                    await user.save()
                    
                    logger.info(
                        f"[RANK RESET] Rank #{rank}: {user.username} "
                        f"(rank_points: {user.rank_points}) rewarded {reward_hc} HC"
                    )
        else:
            logger.info("[RANK RESET] No users with rank_points > 0, skipping rewards")
        
        # STEP 1.5: Archive current leaderboard to history
        try:
            logger.info("[RANK RESET] Archiving current leaderboard...")
            # Re-fetch strictly for history to ensure we get exactly what we want (e.g. top 100)
            history_users = await User.find(
                User.rank_points > 0
            ).sort(-User.rank_points).limit(100).to_list()
            
            if history_users:
                entries = [
                    {
                        "username": u.username,
                        "rank_points": u.rank_points,
                        "level": u.level,
                        "current_hustle": u.current_hustle
                    } for u in history_users
                ]
                
                week_end = datetime.utcnow()
                week_start = week_end - timedelta(days=7)
                
                await LeaderboardHistory(
                    week_start=week_start,
                    week_end=week_end,
                    entries=entries
                ).create()
                logger.info(f"[RANK RESET] Archived {len(entries)} entries to history.")
                
                # Prune old history: Keep last 4 weeks
                all_history = await LeaderboardHistory.find_all().sort(-LeaderboardHistory.week_end).to_list()
                if len(all_history) > 4:
                    to_delete = all_history[4:]
                    for h in to_delete:
                        await h.delete()
                    logger.info(f"[RANK RESET] Pruned {len(to_delete)} old history entries.")
            else:
                logger.info("[RANK RESET] No entries to archive.")
                
        except Exception as e:
            logger.error(f"[RANK RESET] Failed to archive history: {e}")
        
        # STEP 2: Execute the bulk reset operation
        logger.info("[RANK RESET] Starting bulk rank points reset for all users")
        start_time = datetime.utcnow()
        
        # Bulk update all users - set rank_points to 0
        # This is atomic and safe even if multiple instances somehow run it
        result = await User.find_all().update({"$set": {"rank_points": 0}})
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"[RANK RESET] Successfully reset rank points for all users in {duration:.2f} seconds")
        
        # Update last execution time
        await SystemSettings.find_one({"setting_key": lock_key}).update(
            {"$set": {"last_executed_at": datetime.utcnow()}}
        )
        
    except Exception as e:
        logger.error(f"[RANK RESET] Error resetting rank points: {e}", exc_info=True)
    
    finally:
        # Release lock if we acquired it
        if lock_acquired:
            try:
                await SystemSettings.find_one({"setting_key": lock_key}).update(
                    {"$set": {"is_locked": False, "locked_at": None}}
                )
                logger.info("[RANK RESET] Released MongoDB lock")
            except Exception as e:
                logger.warning(f"[RANK RESET] Failed to release MongoDB lock: {e}")

async def check_weekly_rank_reset():
    """
    Checks if we have passed a new Monday 00:00:00 (Angola Time) since the last run.
    If so, it triggers the reset_all_rank_points() function.
    This makes the reset resilient to server restarts or downtime.
    """
    import pytz
    
    lock_key = "rank_reset_lock"
    angola_tz = pytz.timezone('Africa/Luanda')
    
    try:
        # Get the current time in Angola timezone
        now_utc = datetime.utcnow()
        now_angola = now_utc.replace(tzinfo=pytz.utc).astimezone(angola_tz)
        
        # Get the last execution time
        setting = await SystemSettings.find_one({"setting_key": lock_key})
        
        last_executed_at_utc = None
        if setting and setting.last_executed_at:
            last_executed_at_utc = setting.last_executed_at
            
        if not last_executed_at_utc:
            # If it has never run, run it now to establish a baseline
            logger.info("[RANK RESET CHECK] Never run before. Running now.")
            await reset_all_rank_points()
            return
            
        last_executed_angola = last_executed_at_utc.replace(tzinfo=pytz.utc).astimezone(angola_tz)
        
        # Find the most recent target reset time (most recent Monday at 00:00)
        # Determine how many days ago was Monday (0 = Monday, 1 = Tuesday, etc.)
        days_since_monday = now_angola.weekday()
        
        # Go back that many days to get the most recent Monday
        most_recent_monday_date = (now_angola - timedelta(days=days_since_monday)).date()
        
        # Combine with 00:00 time to get the exact target time
        most_recent_reset_target = angola_tz.localize(datetime.combine(most_recent_monday_date, datetime.min.time()))
        
        # If the last time it ran was BEFORE the most recent reset target, we missed a execution
        if last_executed_angola < most_recent_reset_target:
            logger.info(f"[RANK RESET CHECK] Missed a reset event. Last run: {last_executed_angola}. Target: {most_recent_reset_target}. Running now.")
            await reset_all_rank_points()
        else:
            logger.debug(f"[RANK RESET CHECK] Up to date. Last run: {last_executed_angola}")
            
    except Exception as e:
        logger.error(f"[RANK RESET CHECK] Error checking weekly reset: {e}", exc_info=True)

