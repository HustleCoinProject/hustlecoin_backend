from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr

from core.database import get_db_context, AppContext
from core.security import (create_access_token, get_current_user,
                           get_password_hash, verify_password)

# --- Router ---
router = APIRouter(prefix="/api/users", tags=["Users"])

# --- Helper for ObjectID ---
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

# --- Models ---
class UserModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    email: EmailStr
    username: str
    hc_balance: int = 0
    level: int = 1
    language: str = "en"

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserInDB(UserModel):
    hashed_password: str
    lastDailyTap: Optional[datetime] = None
    lastAdWatch: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str

# --- Endpoints ---
@router.post("/register", response_model=UserModel, status_code=201)
async def register_user(user: UserRegister, db_ctx: AppContext = Depends(get_db_context)):
    if await db_ctx.users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user_data = user.dict()
    new_user_data["hashed_password"] = hashed_password
    del new_user_data["password"]
    
    new_user = await db_ctx.users_collection.insert_one(new_user_data)
    created_user = await db_ctx.users_collection.find_one({"_id": new_user.inserted_id})
    return created_user

@router.post("/token", response_model=Token)
async def login_for_access_token(
    db_ctx: AppContext = Depends(get_db_context),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = await db_ctx.users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserModel)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user