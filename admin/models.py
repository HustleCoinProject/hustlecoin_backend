# admin/models.py
from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, field_validator


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


# === CSV Bulk Payout Models ===

class PayoutCSVExportRow(BaseModel):
    """Model representing a single row in the payout CSV export."""
    payout_id: str
    user_id: str
    username: str
    amount_hc: int
    amount_kwanza: float
    payout_method: str
    phone_number: str = ""
    full_name: str = ""
    national_id: str = ""
    bank_iban: str = ""
    bank_name: str = ""
    created_at: str
    # Fields for admin decision
    action: str = ""  # "approve" or "reject" - to be filled by admin
    admin_notes: str = ""
    rejection_reason: str = ""


class PayoutCSVImportRow(BaseModel):
    """Model representing a single row in the payout CSV import."""
    payout_id: str
    action: str  # "approve" or "reject"
    admin_notes: str = ""
    rejection_reason: str = ""
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        if v.lower() not in ['approve', 'reject']:
            raise ValueError('Action must be either "approve" or "reject"')
        return v.lower()
    
    @field_validator('rejection_reason')
    @classmethod
    def validate_rejection_reason(cls, v, info):
        if info.data.get('action') == 'reject' and not v.strip():
            raise ValueError('Rejection reason is required when action is "reject"')
        return v


class BulkPayoutProcessRequest(BaseModel):
    """Request model for bulk payout processing."""
    processed_payouts: List[PayoutCSVImportRow]
    admin_username: str
