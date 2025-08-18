# components/users.py
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field
from beanie import Document, PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List

from core.security import (create_access_token, get_current_user,
                           get_password_hash, verify_password)
from core.translations import translate_text

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
    
    # For streak system
    last_check_in_date: date | None = None # Store only the date, not datetime
    daily_streak: int = 0
    
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
    daily_streak: int
    createdAt: datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str
    current_hustle: str = "Street Vendor"  # Default starting hustle
    language: str = "en"  # Default language

class UserProfileUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = None
    current_hustle: str | None = None
    language: str | None = None

class Token(BaseModel):
    access_token: str
    token_type: str




# A model to represent owned land tiles.
# We'll define the full LandTile document in land.py
class OwnedLand(BaseModel):
    h3_index: str
    purchased_at: datetime



from components.hustles import HUSTLE_CONFIG


@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(user_data: UserRegister):
    if await User.find_one(User.email == user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await User.find_one(User.username == user_data.username):
        raise HTTPException(status_code=400, detail="Username is already taken")

    # Validate that the chosen hustle is a valid level 1 hustle
    level_1_hustles = HUSTLE_CONFIG.get(1, [])
    
    # Check if the provided hustle is valid (either English or translated)
    selected_hustle_english = None
    if user_data.current_hustle in level_1_hustles:
        # It's already in English
        selected_hustle_english = user_data.current_hustle
    else:
        # Check if it's a translated name
        for english_hustle in level_1_hustles:
            if translate_text(english_hustle, user_data.language) == user_data.current_hustle:
                selected_hustle_english = english_hustle
                break
    
    if not selected_hustle_english:
        from core.translations import translate_list
        available_translated = translate_list(level_1_hustles, user_data.language)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid starting hustle. Choose one of: {', '.join(available_translated)}"
        )

    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        current_hustle=selected_hustle_english,  # Store English name
        language=user_data.language
    )
    await user.create()
    
    # Return with translated hustle name
    user_dict = user.dict()
    user_dict["current_hustle"] = translate_text(selected_hustle_english, user_data.language)
    return UserOut(**user_dict)



@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}



@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    # Create a response with translated hustle name
    user_dict = current_user.dict()
    user_dict["current_hustle"] = translate_text(current_user.current_hustle, current_user.language)
    return UserOut(**user_dict)



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
        # Return with translated hustle name
        user_dict = updated_user.dict()
        user_dict["current_hustle"] = translate_text(updated_user.current_hustle, updated_user.language)
        return UserOut(**user_dict)
    
    # Return current user with translated hustle name
    user_dict = current_user.dict()
    user_dict["current_hustle"] = translate_text(current_user.current_hustle, current_user.language)
    return UserOut(**user_dict)



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