import asyncio
import logging
from core.database import init_db
from data.models.models import SystemSettings, User
from admin.background_tasks import reset_all_rank_points

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    
    # Optionally force clear the lock so it runs immediately
    lock_setting = await SystemSettings.find_one({"setting_key": "rank_reset_lock"})
    if lock_setting:
        await lock_setting.update({"$set": {"is_locked": False, "locked_at": None}})
        
    # Give the first test user some points just in case nobody has points
    # This guarantees the reward script actually triggers
    user = await User.find_one({})
    if user and user.rank_points == 0:
        await user.update({"$set": {"rank_points": 500}})
        
    print("Running leaderboard reset script...")
    await reset_all_rank_points()
    print("Leaderboard reset complete.")

if __name__ == "__main__":
    asyncio.run(main())
