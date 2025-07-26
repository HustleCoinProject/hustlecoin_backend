import motor.motor_asyncio
from .config import settings

class AppContext:
    """A context class to hold database collections and other shared resources."""
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_DETAILS)
        self.db = self.client[settings.DATABASE_NAME]

        # Each component will register its collection here
        self.users_collection = self.db.get_collection("users")
        self.quizzes_collection = self.db.get_collection("quizzes")
        self.transactions_collection = self.db.get_collection("transactions")

# Create a single instance that will be shared across the application
db_context = AppContext()

# Dependency to provide the context to endpoints
async def get_db_context():
    return db_context