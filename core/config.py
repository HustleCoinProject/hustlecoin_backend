# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_DETAILS: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 48  # 48 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60  # 60 days

    class Config:
        env_file = ".env"

settings = Settings()