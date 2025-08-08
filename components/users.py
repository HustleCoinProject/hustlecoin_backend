# components/users.py
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from beanie import Document, PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List

from core.security import (create_access_token, get_current_user,
                           get_password_hash, verify_password)

router = APIRouter(prefix="/api/users", tags=["Users"])


# Inventory for items like boosters, etc. for shop
class InventoryItem(BaseModel):
    """Represents a single item in a user's inventory."""
    item_id: str
    quantity: int = 1
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None # For timed boosters


# --- Beanie Document Model ---
class User(Document):
    username: str = Field(..., unique=True)
    email: EmailStr = Field(..., unique=True)
    hashed_password: str
    hc_balance: int = 0
    inventory: List[InventoryItem] = Field(default_factory=list)
    level: int = 1
    current_hustle: str = "Street Vendor" # Default starting hustle
    level_entry_date: datetime = Field(default_factory=datetime.utcnow)
    hc_earned_in_level: int = 0
    language: str = "en"
    task_cooldowns: Dict[str, datetime] = Field(default_factory=dict) # e.g., {"daily_tap": datetime.utcnow()}
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

# --- Pydantic DTOs (Data Transfer Objects) ---
class UserOut(BaseModel):
    id: PydanticObjectId
    username: str
    email: EmailStr
    hc_balance: int = 0
    level: int = 1
    current_hustle: str
    level_entry_date: datetime
    hc_earned_in_level: int
    language: str
    task_cooldowns: Dict[str, datetime]
    createdAt: datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str



# --- Endpoints ---
@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(user_data: UserRegister):
    if await User.find_one(User.email == user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password
    )
    await user.create()
    return user



@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}



@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user



@router.get("/inventory", response_model=List[InventoryItem])
async def get_user_inventory(current_user: User = Depends(get_current_user)):
    """
    Views the current user's inventory of purchased items.
    This endpoint also filters out any expired items before returning them.
    """
    now = datetime.utcnow()
    # Filter inventory to only include items that have not expired.
    active_inventory = [
        item for item in current_user.inventory
        if not item.expires_at or item.expires_at > now
    ]
    return active_inventory