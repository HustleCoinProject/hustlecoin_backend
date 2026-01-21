# core/database.py
import motor.motor_asyncio
from beanie import init_beanie
from .config import settings

async def init_db():
    """Initializes the Beanie ODM and database connection."""
    
    # --- FIX: Import models inside the function to avoid circular imports at startup ---
    from data.models import User, Quiz, LandTile, Payout, SystemSettings, Notification, LeaderboardHistory
    from admin.models import AdminUser


    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_DETAILS)
    await init_beanie(
        database=client.get_database("hustlecoin_db"),
        document_models=[
            User,
            Quiz,
            LandTile,
            Payout,
            SystemSettings,
            AdminUser,
            Notification,
            LeaderboardHistory,
            # Add other Beanie models here as you create them
        ]
    )
