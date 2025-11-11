# admin/auth.py
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status, Depends, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from jose import JWTError, jwt
from core.config import JWT_SECRET_KEY, JWT_ALGORITHM
from .models import AdminUser

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30)  # 30 minutes default
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def authenticate_admin(username: str, password: str) -> Optional[AdminUser]:
    """Authenticate admin user."""
    admin = await AdminUser.find_one(AdminUser.username == username, AdminUser.is_active == True)
    if not admin:
        return None
    if not verify_password(password, admin.hashed_password):
        return None
    return admin

async def get_current_admin_user(request: Request) -> AdminUser:
    """Get current authenticated admin user from cookie."""
    token = request.cookies.get("admin_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/admin/login"}
        )
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_302_FOUND,
                detail="Invalid token",
                headers={"Location": "/admin/login"}
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Invalid token",
            headers={"Location": "/admin/login"}
        )
    
    admin = await AdminUser.find_one(AdminUser.username == username, AdminUser.is_active == True)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Admin not found",
            headers={"Location": "/admin/login"}
        )
    
    return admin
