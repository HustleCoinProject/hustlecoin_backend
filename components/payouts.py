# components/payouts.py
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, validator
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Optional

from data.models import User, Payout
from core.security import get_current_user, get_current_verified_user
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

    crypto_wallet_address: str | None = None
    crypto_network: str | None = None


class UserPayoutInfoUpdate(BaseModel):
    """Update user payout information."""
    phone_number: str | None = Field(None, min_length=9, max_length=20)
    full_name: str | None = Field(None, min_length=2, max_length=100)
    national_id: str | None = Field(None, min_length=5, max_length=50)

    crypto_wallet_address: str | None = Field(None, min_length=10, max_length=100)
    crypto_network: str | None = Field(None, min_length=2, max_length=50)

    @validator('phone_number')
    def validate_phone(cls, v):
        if v is None:
            return v
        # Remove spaces and special characters
        phone = ''.join(filter(str.isdigit, v))
        if len(phone) < 9:
            raise ValueError('Phone number must have at least 9 digits')
        return phone

    @validator('crypto_wallet_address')
    def validate_wallet(cls, v):
        if v is None:
            return v
        # Basic wallet validation
        if len(v) < 10 or len(v) > 100:
            raise ValueError('Wallet address must be between 10 and 100 characters')
        return v


class PayoutRequest(BaseModel):
    """Request for creating a new payout."""
    amount_hc: int = Field(..., gt=0)
    payout_method: str = Field(..., pattern="^(multicaixa_express|crypto_transfer)$")
    
    # Multicaixa Express fields (required if method is multicaixa_express)
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    
    # Crypto transfer fields (required if method is crypto_transfer)
    crypto_wallet_address: str | None = None
    crypto_network: str | None = "Base"  # Default to Base as per requirements

    @validator('amount_hc')
    def validate_amount(cls, v):
        if v < settings.MINIMUM_PAYOUT_HC:
            raise ValueError(f'Minimum payout amount is {settings.MINIMUM_PAYOUT_HC} HC')
        if v > settings.MAXIMUM_PAYOUT_HC:
            raise ValueError(f'Maximum payout amount is {settings.MAXIMUM_PAYOUT_HC} HC')
        return v

    def validate_payout_fields(self):
        """Validate that required fields are provided based on payout method."""
        if self.payout_method == "multicaixa_express":
            if not all([self.phone_number, self.full_name, self.national_id]):
                raise ValueError("Phone number, full name, and national ID are required for Multicaixa Express")
        elif self.payout_method == "crypto_transfer":
            if not self.crypto_wallet_address:
                raise ValueError("Wallet address is required for crypto transfer")
            # Network defaults to "Base" if not provided, but we ensure it's set
            if not self.crypto_network:
                self.crypto_network = "Base"


class UserPayoutInfo(BaseModel):
    """User's saved payout information."""
    phone_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None

    crypto_wallet_address: str | None = None
    crypto_network: str | None = None
    
    # Calculated fields
    available_balance_hc: int
    available_balance_kwanza: float
    min_payout_hc: int
    min_payout_kwanza: float
    conversion_rate: float


# --- Helper Functions ---

def is_sunday_angola_time() -> bool:
    """Check if current time is Sunday in Angola timezone (WAT - West Africa Time, UTC+1)."""
    try:
        angola_tz = ZoneInfo("Africa/Luanda")
        angola_now = datetime.now(angola_tz)
        return angola_now.weekday() == 6  # 6 = Sunday (0 = Monday)
    except Exception:
        # Fallback to UTC+1 if ZoneInfo fails
        from datetime import timezone, timedelta
        utc_plus_1 = timezone(timedelta(hours=1))
        angola_now = datetime.now(utc_plus_1)
        return angola_now.weekday() == 6


def calculate_kwanza_amount(hc_amount: int) -> float:
    """Convert HC to Kwanza based on current rate."""
    return round(hc_amount / settings.PAYOUT_CONVERSION_RATE, 2)


def get_payout_methods() -> List[PayoutMethodInfo]:
    """Get available payout methods with their requirements."""
    min_kwanza = calculate_kwanza_amount(settings.MINIMUM_PAYOUT_HC)
    return [
        PayoutMethodInfo(
            method="multicaixa_express",
            name="Multicaixa Express",
            description="Transfer to your Multicaixa account using phone number",
            required_fields=["phone_number", "full_name", "national_id"],
            min_amount_kwanza=min_kwanza
        ),
        PayoutMethodInfo(
            method="crypto_transfer",
            name="Crypto Transfer (HC)",
            description="Transfer HustleCoin to your wallet on Base network",
            required_fields=["crypto_wallet_address"],
            min_amount_kwanza=min_kwanza
        )
    ]


# --- Endpoints ---

@router.get("/methods", response_model=List[PayoutMethodInfo])
async def get_available_payout_methods():
    """Get available payout methods and their requirements."""
    return get_payout_methods()


@router.get("/info", response_model=UserPayoutInfo)
async def get_user_payout_info(current_user: User = Depends(get_current_verified_user)):
    """Get user's payout information and available balance."""
    return UserPayoutInfo(
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        national_id=current_user.national_id,

        available_balance_hc=current_user.hc_balance,
        available_balance_kwanza=calculate_kwanza_amount(current_user.hc_balance),
        min_payout_hc=settings.MINIMUM_PAYOUT_HC,
        min_payout_kwanza=calculate_kwanza_amount(settings.MINIMUM_PAYOUT_HC),
        conversion_rate=settings.PAYOUT_CONVERSION_RATE
    )


@router.put("/info", response_model=UserPayoutInfo)
async def update_payout_info(
    payout_info: UserPayoutInfoUpdate,
    current_user: User = Depends(get_current_verified_user)
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
    
    if payout_info.crypto_wallet_address is not None:
        update_fields["crypto_wallet_address"] = payout_info.crypto_wallet_address
    
    if payout_info.crypto_network is not None:
        update_fields["crypto_network"] = payout_info.crypto_network
    
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

        available_balance_hc=current_user.hc_balance,
        available_balance_kwanza=calculate_kwanza_amount(current_user.hc_balance),
        min_payout_hc=settings.MINIMUM_PAYOUT_HC,
        min_payout_kwanza=calculate_kwanza_amount(settings.MINIMUM_PAYOUT_HC),
        conversion_rate=settings.PAYOUT_CONVERSION_RATE
    )


@router.post("/request", response_model=PayoutOut, status_code=status.HTTP_201_CREATED)
async def request_payout(
    payout_request: PayoutRequest,
    current_user: User = Depends(get_current_user)
):
    """Request a new payout."""
    
    # Check if it's Sunday in Angola time
    if not is_sunday_angola_time():
        raise HTTPException(
            status_code=400,
            detail="Payout requests can only be made on Sundays (Angola time)."
        )
    
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
        min_kwanza = calculate_kwanza_amount(settings.MINIMUM_PAYOUT_HC)
        raise HTTPException(
            status_code=400,
            detail=f"Minimum payout amount is {settings.MINIMUM_PAYOUT_HC} HC ({min_kwanza} Kwanza)"
        )
    
    # Check maximum payout amount
    if payout_request.amount_hc > settings.MAXIMUM_PAYOUT_HC:
        max_kwanza = calculate_kwanza_amount(settings.MAXIMUM_PAYOUT_HC)
        raise HTTPException(
            status_code=400,
            detail=f"Maximum payout amount is {settings.MAXIMUM_PAYOUT_HC} HC ({max_kwanza} Kwanza)"
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

        crypto_wallet_address=payout_request.crypto_wallet_address,
        crypto_network=payout_request.crypto_network if payout_request.crypto_network else "Base",
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

    )


@router.get("/history", response_model=List[PayoutOut])
async def get_payout_history(
    current_user: User = Depends(get_current_user)
):
    """Get user's payout history (latest 10 records only)."""
    
    # Fixed limit of 10 to prevent memory issues
    payouts = await Payout.find(
        {"user_id": current_user.id}
    ).sort("-created_at").limit(10).to_list()
    
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
            crypto_wallet_address=payout.crypto_wallet_address,
            crypto_network=payout.crypto_network
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
        crypto_wallet_address=payout.crypto_wallet_address,
        crypto_network=payout.crypto_network
    )


# Helper endpoint for system status (can be useful for monitoring)
@router.get("/system/status", response_model=dict)
async def get_payout_system_status():
    """Get payout system status - useful for monitoring (optimized with aggregation)."""
    
    # Use single aggregation pipeline for all statistics (memory-efficient)
    collection = Payout.get_pymongo_collection()
    
    pipeline = [
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_kwanza": {"$sum": "$amount_kwanza"}
            }
        }
    ]
    
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    # Parse aggregation results
    stats = {
        "pending": 0,
        "completed": 0,
        "rejected": 0,
        "total_completed_kwanza": 0.0,
        "pending_total_kwanza": 0.0
    }
    
    for result in results:
        status = result.get("_id")
        count = result.get("count", 0)
        total_kwanza = result.get("total_kwanza", 0.0)
        
        if status == "pending":
            stats["pending"] = count
            stats["pending_total_kwanza"] = total_kwanza
        elif status == "completed":
            stats["completed"] = count
            stats["total_completed_kwanza"] = total_kwanza
        elif status == "rejected":
            stats["rejected"] = count
    
    return {
        "system_name": "HustleCoin Payout System",
        "status": "operational",
        "conversion_rate": settings.PAYOUT_CONVERSION_RATE,
        "minimum_payout_hc": settings.MINIMUM_PAYOUT_HC,
        "minimum_payout_kwanza": calculate_kwanza_amount(settings.MINIMUM_PAYOUT_HC),
        "statistics": stats
    }
