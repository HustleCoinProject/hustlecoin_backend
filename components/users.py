# components/users.py
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from beanie import Document, PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from core.security import (create_access_token, get_current_user,
                           get_password_hash, verify_password)

router = APIRouter(prefix="/api/users", tags=["Users"])

# --- Beanie Document Model ---
class User(Document):
    username: str = Field(..., unique=True)
    email: EmailStr = Field(..., unique=True)
    hashed_password: str
    hc_balance: int = 0
    level: int = 1
    language: str = "en"
    lastDailyTap: datetime | None = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

# --- Pydantic DTOs (Data Transfer Objects) ---
class UserOut(BaseModel):
    id: PydanticObjectId
    username: str
    email: EmailStr
    hc_balance: int
    level: int

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

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user