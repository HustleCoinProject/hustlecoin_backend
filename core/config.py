from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGO_DETAILS: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "hustlecoin_db"
    SECRET_KEY: str = "a_very_secret_key_for_jwt_tokens"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    class Config:
        env_file = ".env"

settings = Settings()