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
from beanie import Document, PydanticObjectId
from beanie.odm.fields import Indexed as IndexedField
from typing import Dict, List, Annotated


# ===== USER MODEL =====

# Inventory for items like boosters, etc. for shop
class InventoryItem(BaseModel):
    """Represents a single item in a user's inventory."""
    item_id: str
    quantity: int = 1
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None # For timed boosters


class User(Document):
    username: Annotated[str, IndexedField(unique=True)] = Field(..., min_length=3, max_length=30)
    email: Annotated[EmailStr, IndexedField(unique=True)] = Field(..., max_length=254)
    hashed_password: str
    hc_balance: int = 0
    rank_points: Annotated[int, IndexedField()] = 0  # Points that reflect user's activity and importance
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
    
    # For safe lock system
    safe_lock_amount: int = 0  # HC amount currently locked in safe
    safe_lock_locked_until: datetime | None = None  # When the safe lock can be claimed
    
    # Payout information fields
    phone_number: str | None = None  # For Angola Multicaixa Express transfers
    full_name: str | None = None  # Full name for transfers
    national_id: str | None = None  # National ID for verification
    
    # Bank transfer information
    bank_iban: str | None = None  # IBAN for bank transfers
    bank_name: str | None = None  # Bank name
    
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
    h3_index: Annotated[str, IndexedField(unique=True)]
    owner_id: Annotated[PydanticObjectId, IndexedField()]
    purchased_at: datetime = Field(default_factory=datetime.utcnow)
    purchase_price: int
    last_income_payout_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "land_tiles"


# ===== PAYOUT MODEL =====

class Payout(Document):
    user_id: Annotated[PydanticObjectId, IndexedField()]
    amount_hc: int  # Amount in HustleCoin
    amount_kwanza: float  # Amount in Kwanza (HC / conversion_rate)
    conversion_rate: float = 10.0  # Default: 1 Kwanza = 10 HC
    
    # Payout method: "multicaixa_express" or "bank_transfer"
    payout_method: str
    
    # Multicaixa Express fields
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    
    # Bank transfer fields
    bank_iban: str | None = None
    bank_name: str | None = None
    
    # Status: "pending" | "completed" | "rejected"
    status: Annotated[str, IndexedField()] = "pending"
    
    # Admin notes and processing info
    admin_notes: str | None = None
    processed_by: str | None = None  # Admin username who processed it
    processed_at: datetime | None = None
    
    # Rejection reason (if status is rejected)
    rejection_reason: str | None = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payouts"
        indexes = [
            [("user_id", 1), ("created_at", -1)],  # For user payout history
            [("status", 1), ("created_at", -1)]      # For admin pending payouts
        ]
