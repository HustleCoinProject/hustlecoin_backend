# data/models/models.py
# All database models (Document classes) are consolidated here to avoid circular imports

from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field
try:
    # Pydantic v2
    from pydantic import field_validator as validator
except Exception:  # pragma: no cover
    # Pydantic v1 fallback
    from pydantic import validator
from beanie import Document, PydanticObjectId, Indexed
from typing import Dict, List


# ===== USER MODEL =====

# Inventory for items like boosters, etc. for shop
class InventoryItem(BaseModel):
    """Represents a single item in a user's inventory."""
    item_id: str
    quantity: int = 1
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None # For timed boosters


class User(Document):
    username: str = Field(..., unique=True, min_length=3, max_length=30)
    email: EmailStr = Field(..., unique=True, max_length=254)
    hashed_password: str
    hc_balance: int = 0
    inventory: List[InventoryItem] = Field(default_factory=list)
    level: int = 1
    current_hustle: str = "Street Vendor" # Default starting hustle
    level_entry_date: datetime = Field(default_factory=datetime.utcnow)
    hc_earned_in_level: int = 0
    language: str = "en"
    task_cooldowns: Dict[str, datetime] = Field(default_factory=dict) # e.g., {"daily_tap": datetime.utcnow()}
    
    # For streak system
    last_check_in_date: date | None = None # Store only the date, not datetime
    daily_streak: int = 0
    
    # For daily tap system
    daily_tap_earnings: int = 0  # HC earned from taps today
    last_tap_reset_date: date | None = None  # Last date when tap earnings were reset
    
    # For land income claiming system
    last_land_claim_at: datetime | None = None  # Last time user claimed land income
    
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"


# ===== QUIZ MODEL =====

class Quiz(Document):
    question_pt: str
    question_en: str
    options_pt: List[str]
    options_en: List[str]
    correctAnswerIndex: int
    isActive: bool = True

    class Settings:
        name = "quizzes" # This collection will still exist


# ===== LAND TILE MODEL =====

class LandTile(Document):
    h3_index: Indexed(str, unique=True)
    owner_id: Indexed(PydanticObjectId)
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    purchase_price: int
    last_income_payout_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "land_tiles"
