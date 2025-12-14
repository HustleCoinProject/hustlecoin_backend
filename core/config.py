# core/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    MONGO_DETAILS: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 48  # 48 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60  # 60 days
    
    # Firebase configuration (optional)
    FIREBASE_SERVICE_ACCOUNT_BASE64: Optional[str] = None  # Base64 encoded service account (for production)
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None  # File path to service account (for local dev)
    
    # Land configuration
    LAND_PRICE: int = 500  # Price in HustleCoin to buy one tile
    LAND_SELL_PRICE: int = 400  # Price for selling a tile back to the system
    LAND_INCOME_PER_DAY: int = 50
    LAND_INCOME_ACCUMULATE: bool = False  # If True, income accumulates over days; if False, fixed daily amount
    
    # Payout configuration
    PAYOUT_CONVERSION_RATE: float = 10.0  # 1 Kwanza = 10 HC
    MINIMUM_PAYOUT_HC: int = 10000  # Minimum HC required for payout (10,000 HC = 1,000 Kwanza)
    MAXIMUM_PAYOUT_HC: int = 30000  # Maximum HC allowed per payout (30,000 HC = 3,000 Kwanza)
    
    # Redis configuration for rate limiting
    REDIS_URL: str = "redis://localhost:6379/0"
    
    @property
    def LAND_INCOME_PER_SECOND(self) -> float:
        """Calculate land income per second from daily income"""
        return self.LAND_INCOME_PER_DAY / (24 * 3600)

    class Config:
        env_file = ".env"

settings = Settings()

# Export commonly used values for admin module
JWT_SECRET_KEY = settings.SECRET_KEY
JWT_ALGORITHM = settings.ALGORITHM