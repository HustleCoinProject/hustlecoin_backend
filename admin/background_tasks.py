# admin/background_tasks.py
from typing import List, Dict
from datetime import datetime, timedelta
from beanie import PydanticObjectId
from data.models.models import Payout, User, SystemSettings
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
