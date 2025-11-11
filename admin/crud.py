# admin/crud.py
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from beanie import Document, PydanticObjectId
from bson import ObjectId
from .registry import AdminRegistry
import json
from datetime import datetime


# This old AdminCRUD class is not needed with the new registry system
# The admin routes now use AdminRegistry directly


# Admin User Management Functions
from passlib.context import CryptContext
from .models import AdminUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_admin_user(
    username: str,
    email: str,
    password: str,
    is_superuser: bool = False
) -> AdminUser:
    """Create a new admin user."""
    # Check if user already exists
    existing_user = await AdminUser.find_one(AdminUser.username == username)
    if existing_user:
        raise ValueError(f"Admin user with username '{username}' already exists")
    
    existing_email = await AdminUser.find_one(AdminUser.email == email)
    if existing_email:
        raise ValueError(f"Admin user with email '{email}' already exists")
    
    # Create new admin user
    hashed_password = pwd_context.hash(password)
    admin_user = AdminUser(
        username=username,
        email=email,
        hashed_password=hashed_password,
        is_superuser=is_superuser,
        is_active=True
    )
    
    await admin_user.save()
    return admin_user

async def get_admin_by_username(username: str) -> Optional[AdminUser]:
    """Get admin user by username."""
    return await AdminUser.find_one(AdminUser.username == username)

async def update_admin_password(username: str, new_password: str) -> bool:
    """Update admin user password."""
    admin_user = await get_admin_by_username(username)
    if not admin_user:
        return False
    
    admin_user.hashed_password = pwd_context.hash(new_password)
    await admin_user.save()
    return True

async def list_admin_users():
    """List all admin users."""
    return await AdminUser.find().to_list()
