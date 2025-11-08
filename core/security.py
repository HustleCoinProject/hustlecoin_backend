# core/security.py
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

# --- FIX: Use TYPE_CHECKING to prevent circular import at runtime ---
if TYPE_CHECKING:
    from data.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# The return type annotation '-> "User"' uses a forward reference string
# This is another way to avoid direct imports at the top level.
async def get_current_user(token: str = Depends(oauth2_scheme)) -> "User":
    # --- FIX: Import User model here, inside the function scope ---
    from data.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if username is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await User.find_one(User.username == username)
    if user is None:
        raise credentials_exception
    return user

async def verify_refresh_token(token: str) -> str:
    """Verify refresh token and return username if valid."""
    from data.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if username is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Verify user still exists
    user = await User.find_one(User.username == username)
    if user is None:
        raise credentials_exception
    
    return username