# core/database.py
import motor.motor_asyncio
from beanie import init_beanie
from .config import settings

async def init_db():
    """Initializes the Beanie ODM and database connection."""
    
    # --- FIX: Import models inside the function to avoid circular imports at startup ---
    from components.users import User
    from components.tasks import Quiz


    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_DETAILS)
    await init_beanie(
        database=client.get_database("hustlecoin_db"),
        document_models=[
            User,
            Quiz,
            # Add other Beanie models here as you create them
        ]
    )
