# components/users.py
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field
try:
    # Pydantic v2
    from pydantic import field_validator as validator
except Exception:  # pragma: no cover
    # Pydantic v1 fallback
    from pydantic import validator
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List

from data.models import User, InventoryItem
from core.security import (create_access_token, create_refresh_token, get_current_user,
                           get_password_hash, verify_password, verify_refresh_token)
from core.rate_limiter_slowapi import auth_limiter
from core.game_logic import GameLogic
from components.shop import SHOP_ITEMS_CONFIG
from core.translations import translate_text

router = APIRouter(prefix="/api/users", tags=["Users"])


class InventoryItemOut(BaseModel):
    """Compact inventory item response for frontend display."""
    item_id: str
    quantity: int
    purchased_at: datetime
    expires_at: datetime | None = None
    
    # Item details for display
    name: str
    description: str
    item_type: str
    
    # Time remaining for active items
    time_remaining_seconds: float | None = None

# --- Pydantic DTOs (Data Transfer Objects) ---
class UserOut(BaseModel):
    id: PydanticObjectId
    username: str
    email: EmailStr
    hc_balance: int = 0
    rank_points: int = 0
    level: int = 1
    current_hustle: Dict[str, str]  # Changed to Dict[str, str] for localized key-value pair
    level_entry_date: datetime
    hc_earned_in_level: int
    language: str
    task_cooldowns: Dict[str, datetime]
    daily_streak: int
    daily_tap_earnings: int = 0
    last_tap_reset_date: date | None = None
    last_land_claim_at: datetime | None = None
    safe_lock_amount: int = 0
    safe_lock_locked_until: datetime | None = None
    createdAt: datetime

class UserRegister(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    username: str = Field(..., min_length=3, max_length=30)
    current_hustle: str = "Street Vendor"  # Default starting hustle
    language: str = "en"  # Default language

    @validator("email")
    def validate_email_length(cls, v: EmailStr) -> EmailStr:
        # Practical maximum per RFC guidelines is 254; local part <= 64
        email_str = str(v)
        if len(email_str) > 254:
            raise ValueError("Email must be at most 254 characters long")
        local_part = email_str.split("@")[0]
        if len(local_part) > 64:
            raise ValueError("Email local part must be at most 64 characters long")
        return v

class UserProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=30)
    email: EmailStr | None = Field(default=None, max_length=254)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    current_hustle: str | None = None
    language: str | None = None

    @validator("email")
    def validate_email_length_optional(cls, v: EmailStr | None) -> EmailStr | None:
        if v is None:
            return v
        email_str = str(v)
        if len(email_str) > 254:
            raise ValueError("Email must be at most 254 characters long")
        local_part = email_str.split("@")[0]
        if len(local_part) > 64:
            raise ValueError("Email local part must be at most 64 characters long")
        return v

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str






# A model to represent owned land tiles.
# We'll define the full LandTile document in land.py
class OwnedLand(BaseModel):
    h3_index: str
    purchased_at: datetime



from components.hustles import HUSTLE_CONFIG


def _create_user_out_response(user: User) -> Dict:
    """Helper function to create UserOut response with localized hustle name."""
    user_dict = user.dict()
    # Convert current_hustle from string to localized key-value pair
    user_dict["current_hustle"] = {user.current_hustle: translate_text(user.current_hustle, user.language)}
    return user_dict


@router.post("/register", response_model=UserOut, status_code=201)
@auth_limiter.limit("5/minute")
async def register_user(request: Request, user_data: UserRegister):
    if await User.find_one(User.email == user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await User.find_one(User.username == user_data.username):
        raise HTTPException(status_code=400, detail="Username is already taken")

    # Validate that the chosen hustle is a valid level 1 hustle
    level_1_hustles = HUSTLE_CONFIG.get(1, [])
    if user_data.current_hustle not in level_1_hustles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid starting hustle. Choose one of: {', '.join(level_1_hustles)}"
        )

    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        current_hustle=user_data.current_hustle,
        language=user_data.language
    )
    await user.create()
    return _create_user_out_response(user)



@router.post("/login", response_model=Token)
@auth_limiter.limit("5/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
async def refresh_access_token(refresh_data: RefreshTokenRequest):
    """
    Refresh access token using a valid refresh token.
    Returns a new access token and refresh token pair.
    """
    try:
        # Verify the refresh token and get username
        username = await verify_refresh_token(refresh_data.refresh_token)
        
        # Create new tokens
        access_token = create_access_token(data={"sub": username})
        refresh_token = create_refresh_token(data={"sub": username})
        
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
    
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )



@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return _create_user_out_response(current_user)



# Edit profile endpoint
@router.put("/profile", response_model=UserOut)
async def update_profile(profile_data: UserProfileUpdate, current_user: User = Depends(get_current_user)):
    """
    Update user profile information (username, email, password, current_hustle, language).
    Only updates fields that are provided (not None).
    Password changes require the current password for verification.
    """
    update_fields = {}
    
    # Handle password change
    if profile_data.new_password is not None:
        # Current password must be provided to change the password
        if profile_data.current_password is None:
            raise HTTPException(status_code=400, detail="Current password is required to set a new password")
        
        # Verify current password
        if not verify_password(profile_data.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Set new hashed password
        update_fields["hashed_password"] = get_password_hash(profile_data.new_password)
    
    # Handle email change
    if profile_data.email is not None and profile_data.email != current_user.email:
        # Check if email is already used
        existing_user = await User.find_one(User.email == profile_data.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email is already registered")
        
        update_fields["email"] = profile_data.email
    
    # Handle username change
    if profile_data.username is not None and profile_data.username != current_user.username:
        # Check if username is already taken by another user
        existing_user = await User.find_one(User.username == profile_data.username)
        if existing_user:
            raise HTTPException(status_code=400, detail="Username is already taken")
        
        update_fields["username"] = profile_data.username
    
    # Handle other profile fields
    if profile_data.current_hustle is not None:
        update_fields["current_hustle"] = profile_data.current_hustle
    
    if profile_data.language is not None:
        update_fields["language"] = profile_data.language
    
    # Update user if there are changes
    if update_fields:
        await current_user.update({"$set": update_fields})
        # Refetch the user to get updated data
        updated_user = await User.get(current_user.id)
        return _create_user_out_response(updated_user)
    
    return _create_user_out_response(current_user)



@router.get("/inventory", response_model=List[InventoryItemOut])
async def get_user_inventory(current_user: User = Depends(get_current_user)):
    """
    Views the current user's active inventory items for frontend display.
    Only returns non-expired items with essential display information.
    """
    now = datetime.utcnow()
    user_language = current_user.language
    active_inventory = []
    
    for item in current_user.inventory:
        # Skip expired items completely
        if item.expires_at and item.expires_at <= now:
            continue
            
        # Get item configuration from shop
        item_config = SHOP_ITEMS_CONFIG.get(item.item_id)
        if not item_config:
            # Skip items that are no longer in the shop config
            continue
        
        # Calculate time remaining for active items
        time_remaining_seconds = None
        if item.expires_at:
            time_remaining_seconds = (item.expires_at - now).total_seconds()
        
        # Create compact inventory item for frontend
        inventory_item = InventoryItemOut(
            item_id=item.item_id,
            quantity=item.quantity,
            purchased_at=item.purchased_at,
            expires_at=item.expires_at,
            
            # Translated item details for display
            name=translate_text(item_config["name"], user_language),
            description=translate_text(item_config["description"], user_language),
            item_type=item_config["item_type"],
            
            # Time remaining for countdown displays
            time_remaining_seconds=time_remaining_seconds
        )
        
        active_inventory.append(inventory_item)
    
    # Sort by purchase date (newest first)
    active_inventory.sort(key=lambda x: -x.purchased_at.timestamp())
    
    return active_inventory