# components/payouts.py
from datetime import datetime
from pydantic import BaseModel, Field, validator
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Optional

from data.models import User, Payout
from core.security import get_current_user
from core.config import settings
from core.translations import translate_text

router = APIRouter(prefix="/api/payouts", tags=["Payouts"])


# --- Pydantic DTOs ---

class PayoutMethodInfo(BaseModel):
    """Information about available payout methods."""
    method: str
    name: str
    description: str
    required_fields: List[str]
    min_amount_kwanza: float


class PayoutOut(BaseModel):
    """Payout information for user display."""
    id: PydanticObjectId
    amount_hc: int
    amount_kwanza: float
    payout_method: str
    status: str
    created_at: datetime
    processed_at: datetime | None = None
    rejection_reason: str | None = None
    
    # Only show sensitive info to the payout owner
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    bank_iban: str | None = None
    bank_name: str | None = None


class UserPayoutInfoUpdate(BaseModel):
    """Update user payout information."""
    phone_number: str | None = Field(None, min_length=9, max_length=20)
    full_name: str | None = Field(None, min_length=2, max_length=100)
    national_id: str | None = Field(None, min_length=5, max_length=50)
    bank_iban: str | None = Field(None, min_length=15, max_length=34)
    bank_name: str | None = Field(None, min_length=2, max_length=100)

    @validator('phone_number')
    def validate_phone(cls, v):
        if v is None:
            return v
        # Remove spaces and special characters
        phone = ''.join(filter(str.isdigit, v))
        if len(phone) < 9:
            raise ValueError('Phone number must have at least 9 digits')
        return phone

    @validator('bank_iban')
    def validate_iban(cls, v):
        if v is None:
            return v
        # Basic IBAN validation - remove spaces and check format
        iban = v.replace(' ', '').upper()
        if len(iban) < 15 or len(iban) > 34:
            raise ValueError('IBAN must be between 15 and 34 characters')
        return iban


class PayoutRequest(BaseModel):
    """Request for creating a new payout."""
    amount_hc: int = Field(..., gt=0)
    payout_method: str = Field(..., pattern="^(multicaixa_express|bank_transfer)$")
    
    # Multicaixa Express fields (required if method is multicaixa_express)
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    
    # Bank transfer fields (required if method is bank_transfer)
    bank_iban: str | None = None
    bank_name: str | None = None

    @validator('amount_hc')
    def validate_amount(cls, v):
        if v < settings.MINIMUM_PAYOUT_HC:
            raise ValueError(f'Minimum payout amount is {settings.MINIMUM_PAYOUT_HC} HC')
        return v

    def validate_payout_fields(self):
        """Validate that required fields are provided based on payout method."""
        if self.payout_method == "multicaixa_express":
            if not all([self.phone_number, self.full_name, self.national_id]):
                raise ValueError("Phone number, full name, and national ID are required for Multicaixa Express")
        elif self.payout_method == "bank_transfer":
            if not all([self.bank_iban, self.bank_name]):
                raise ValueError("Bank IBAN and bank name are required for bank transfer")


class UserPayoutInfo(BaseModel):
    """User's saved payout information."""
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    bank_iban: str | None = None
    bank_name: str | None = None
    
    # Calculated fields
    available_balance_hc: int
    available_balance_kwanza: float
    min_payout_hc: int
    min_payout_kwanza: float
    conversion_rate: float


# --- Helper Functions ---

def calculate_kwanza_amount(hc_amount: int) -> float:
    """Convert HC to Kwanza based on current rate."""
    return round(hc_amount / settings.PAYOUT_CONVERSION_RATE, 2)


def get_payout_methods() -> List[PayoutMethodInfo]:
    """Get available payout methods with their requirements."""
    return [
        PayoutMethodInfo(
            method="multicaixa_express",
            name="Multicaixa Express",
            description="Transfer to your Multicaixa account using phone number",
            required_fields=["phone_number", "full_name", "national_id"],
            min_amount_kwanza=settings.MINIMUM_PAYOUT_KWANZA
        ),
        PayoutMethodInfo(
            method="bank_transfer",
            name="Bank Transfer",
            description="Transfer to your bank account using IBAN",
            required_fields=["bank_iban", "bank_name"],
            min_amount_kwanza=settings.MINIMUM_PAYOUT_KWANZA
        )
    ]


# --- Endpoints ---

@router.get("/methods", response_model=List[PayoutMethodInfo])
async def get_available_payout_methods():
    """Get available payout methods and their requirements."""
    return get_payout_methods()


@router.get("/info", response_model=UserPayoutInfo)
async def get_user_payout_info(current_user: User = Depends(get_current_user)):
    """Get user's payout information and available balance."""
    return UserPayoutInfo(
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        national_id=current_user.national_id,
        bank_iban=current_user.bank_iban,
        bank_name=current_user.bank_name,
        available_balance_hc=current_user.hc_balance,
        available_balance_kwanza=calculate_kwanza_amount(current_user.hc_balance),
        min_payout_hc=settings.MINIMUM_PAYOUT_HC,
        min_payout_kwanza=settings.MINIMUM_PAYOUT_KWANZA,
        conversion_rate=settings.PAYOUT_CONVERSION_RATE
    )


@router.put("/info", response_model=UserPayoutInfo)
async def update_payout_info(
    payout_info: UserPayoutInfoUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update user's payout information."""
    update_fields = {}
    
    # Update only provided fields
    if payout_info.phone_number is not None:
        update_fields["phone_number"] = payout_info.phone_number
    
    if payout_info.full_name is not None:
        update_fields["full_name"] = payout_info.full_name
    
    if payout_info.national_id is not None:
        update_fields["national_id"] = payout_info.national_id
    
    if payout_info.bank_iban is not None:
        update_fields["bank_iban"] = payout_info.bank_iban
    
    if payout_info.bank_name is not None:
        update_fields["bank_name"] = payout_info.bank_name
    
    # Update user if there are changes
    if update_fields:
        await current_user.update({"$set": update_fields})
        # Refetch user to get updated data
        updated_user = await User.get(current_user.id)
        current_user = updated_user
    
    return UserPayoutInfo(
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        national_id=current_user.national_id,
        bank_iban=current_user.bank_iban,
        bank_name=current_user.bank_name,
        available_balance_hc=current_user.hc_balance,
        available_balance_kwanza=calculate_kwanza_amount(current_user.hc_balance),
        min_payout_hc=settings.MINIMUM_PAYOUT_HC,
        min_payout_kwanza=settings.MINIMUM_PAYOUT_KWANZA,
        conversion_rate=settings.PAYOUT_CONVERSION_RATE
    )


@router.post("/request", response_model=PayoutOut, status_code=status.HTTP_201_CREATED)
async def request_payout(
    payout_request: PayoutRequest,
    current_user: User = Depends(get_current_user)
):
    """Request a new payout."""
    
    # Validate payout fields based on method
    try:
        payout_request.validate_payout_fields()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if user has sufficient balance
    if current_user.hc_balance < payout_request.amount_hc:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: {current_user.hc_balance} HC, Requested: {payout_request.amount_hc} HC"
        )
    
    # Check minimum payout amount
    if payout_request.amount_hc < settings.MINIMUM_PAYOUT_HC:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum payout amount is {settings.MINIMUM_PAYOUT_HC} HC ({settings.MINIMUM_PAYOUT_KWANZA} Kwanza)"
        )
    
    # Check for pending payouts (limit one pending payout per user)
    existing_pending = await Payout.find_one({
        "user_id": current_user.id,
        "status": "pending"
    })
    
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending payout request. Please wait for it to be processed."
        )
    
    # Calculate Kwanza amount
    kwanza_amount = calculate_kwanza_amount(payout_request.amount_hc)
    
    # Create payout record
    payout = Payout(
        user_id=current_user.id,
        amount_hc=payout_request.amount_hc,
        amount_kwanza=kwanza_amount,
        conversion_rate=settings.PAYOUT_CONVERSION_RATE,
        payout_method=payout_request.payout_method,
        phone_number=payout_request.phone_number,
        full_name=payout_request.full_name,
        national_id=payout_request.national_id,
        bank_iban=payout_request.bank_iban,
        bank_name=payout_request.bank_name,
        status="pending"
    )
    
    await payout.create()
    
    # Deduct HC from user balance
    await current_user.update({"$inc": {"hc_balance": -payout_request.amount_hc}})
    
    return PayoutOut(
        id=payout.id,
        amount_hc=payout.amount_hc,
        amount_kwanza=payout.amount_kwanza,
        payout_method=payout.payout_method,
        status=payout.status,
        created_at=payout.created_at,
        phone_number=payout.phone_number,
        full_name=payout.full_name,
        national_id=payout.national_id,
        bank_iban=payout.bank_iban,
        bank_name=payout.bank_name
    )


@router.get("/history", response_model=List[PayoutOut])
async def get_payout_history(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get user's payout history."""
    
    payouts = await Payout.find(
        {"user_id": current_user.id}
    ).sort("-created_at").limit(limit).skip(offset).to_list()
    
    return [
        PayoutOut(
            id=payout.id,
            amount_hc=payout.amount_hc,
            amount_kwanza=payout.amount_kwanza,
            payout_method=payout.payout_method,
            status=payout.status,
            created_at=payout.created_at,
            processed_at=payout.processed_at,
            rejection_reason=payout.rejection_reason,
            phone_number=payout.phone_number,
            full_name=payout.full_name,
            national_id=payout.national_id,
            bank_iban=payout.bank_iban,
            bank_name=payout.bank_name
        )
        for payout in payouts
    ]


@router.get("/{payout_id}", response_model=PayoutOut)
async def get_payout_details(
    payout_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific payout."""
    
    payout = await Payout.find_one({
        "_id": payout_id,
        "user_id": current_user.id
    })
    
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    
    return PayoutOut(
        id=payout.id,
        amount_hc=payout.amount_hc,
        amount_kwanza=payout.amount_kwanza,
        payout_method=payout.payout_method,
        status=payout.status,
        created_at=payout.created_at,
        processed_at=payout.processed_at,
        rejection_reason=payout.rejection_reason,
        phone_number=payout.phone_number,
        full_name=payout.full_name,
        national_id=payout.national_id,
        bank_iban=payout.bank_iban,
        bank_name=payout.bank_name
    )


# Helper endpoint for system status (can be useful for monitoring)
@router.get("/system/status", response_model=dict)
async def get_payout_system_status():
    """Get payout system status - useful for monitoring."""
    
    # Count payouts by status
    pending_count = await Payout.find({"status": "pending"}).count()
    completed_count = await Payout.find({"status": "completed"}).count()
    rejected_count = await Payout.find({"status": "rejected"}).count()
    
    # Calculate total amounts
    completed_payouts = await Payout.find({"status": "completed"}).to_list()
    total_completed_kwanza = sum(p.amount_kwanza for p in completed_payouts)
    
    pending_payouts = await Payout.find({"status": "pending"}).to_list()
    pending_total_kwanza = sum(p.amount_kwanza for p in pending_payouts)
    
    return {
        "system_name": "HustleCoin Payout System",
        "status": "operational",
        "conversion_rate": settings.PAYOUT_CONVERSION_RATE,
        "minimum_payout_hc": settings.MINIMUM_PAYOUT_HC,
        "minimum_payout_kwanza": settings.MINIMUM_PAYOUT_KWANZA,
        "statistics": {
            "pending": pending_count,
            "completed": completed_count,
            "rejected": rejected_count,
            "total_completed_kwanza": total_completed_kwanza,
            "pending_total_kwanza": pending_total_kwanza
        }
    }
