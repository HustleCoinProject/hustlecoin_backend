# admin/models.py
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import BaseModel, Field


class AdminUser(Document):
    """Admin user model for the admin panel."""
    username: str = Field(..., unique=True, min_length=3, max_length=30)
    email: str = Field(..., unique=True)
    hashed_password: str
    is_superuser: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    class Settings:
        name = "admin_users"


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    is_superuser: bool = False


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
