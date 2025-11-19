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


# Payout Management Functions
from data.models.models import Payout, User

async def get_pending_payouts() -> List[Payout]:
    """Get all pending payouts for admin review."""
    return await Payout.find({"status": "pending"}).sort("-created_at").to_list()

async def process_payout(
    payout_id: PydanticObjectId,
    admin_username: str,
    action: str,  # "approve" or "reject"
    admin_notes: str = None,
    rejection_reason: str = None
) -> Payout:
    """Process a payout request (approve or reject)."""
    print(f"Starting payout processing for ID: {payout_id}, action: {action}")
    
    payout = await Payout.get(payout_id)
    if not payout:
        print(f"Payout not found: {payout_id}")
        raise HTTPException(status_code=404, detail="Payout not found")
    
    print(f"Found payout: ID={payout.id}, status={payout.status}, amount_hc={payout.amount_hc}")
    
    if payout.status != "pending":
        print(f"Payout is not in pending status. Current status: {payout.status}")
        raise HTTPException(status_code=400, detail=f"Payout is not in pending status. Current status: {payout.status}")
    
    user = await User.get(payout.user_id)
    if not user:
        print(f"User not found: {payout.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    
    print(f"Found user: ID={user.id}, hc_balance={user.hc_balance}")
    
    now = datetime.utcnow()
    
    if action == "approve":
        print(f"Approving payout: {payout_id}")
        # Mark as completed directly
        payout.status = "completed"
        payout.processed_by = admin_username
        payout.processed_at = now
        if admin_notes:
            payout.admin_notes = admin_notes
        print(f"Payout approved and set to completed status")
    
    elif action == "reject":
        print(f"Rejecting payout: {payout_id}, returning {payout.amount_hc} HC to user {user.id}")
        # Reject payout and return HC to user
        payout.status = "rejected"
        payout.processed_by = admin_username
        payout.processed_at = now
        payout.rejection_reason = rejection_reason or "No reason provided"
        if admin_notes:
            payout.admin_notes = admin_notes
        
        # Return HC to user balance
        old_balance = user.hc_balance
        await user.update({"$inc": {"hc_balance": payout.amount_hc}})
        
        # Refresh user to verify balance update
        updated_user = await User.get(user.id)
        print(f"Balance updated: {old_balance} -> {updated_user.hc_balance} (+{payout.amount_hc} HC)")
        
    else:
        print(f"Invalid action: {action}")
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")
    
    payout.updated_at = now
    await payout.save()
    
    print(f"Payout processed successfully: ID={payout.id}, status={payout.status}")
    return payout



async def get_payout_statistics() -> Dict[str, Any]:
    """Get payout statistics for admin dashboard."""
    stats = {}
    
    # Count payouts by status
    for status in ["pending", "completed", "rejected"]:
        count = await Payout.find({"status": status}).count()
        stats[f"{status}_count"] = count
    
    # Total amounts
    completed_payouts = await Payout.find({"status": "completed"}).to_list()
    stats["total_completed_hc"] = sum(p.amount_hc for p in completed_payouts)
    stats["total_completed_kwanza"] = sum(p.amount_kwanza for p in completed_payouts)
    
    pending_payouts = await Payout.find({"status": "pending"}).to_list()
    stats["pending_total_hc"] = sum(p.amount_hc for p in pending_payouts)
    stats["pending_total_kwanza"] = sum(p.amount_kwanza for p in pending_payouts)
    
    return stats
