# admin/crud.py
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from beanie import Document, PydanticObjectId
from bson import ObjectId
from .registry import AdminRegistry
import json
from datetime import datetime
from data.models.models import Payout, User, Notification


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
        raise HTTPException(status_code=400, detail=f"Cannot process payout {payout_id}: already {payout.status}")
    
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
        
        # Create notification for user
        notification = Notification(
            user_id=user.id,
            title="Payout Approved!",
            message=f"Your payout request for {payout.amount_hc} HC has been approved and processed.",
            type="payout_status",
            metadata={"payout_id": str(payout.id), "status": "completed"}
        )
        await notification.insert()
        print(f"Notification created for user {user.id}")
    
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
        
        # Create notification for user
        notification = Notification(
            user_id=user.id,
            title="Payout Rejected",
            message=f"Your payout request for {payout.amount_hc} HC was rejected. Reason: {payout.rejection_reason}. The amount has been returned to your balance.",
            type="payout_status",
            metadata={"payout_id": str(payout.id), "status": "rejected"}
        )
        await notification.insert()
        print(f"Notification created for user {user.id}")
        
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


# === CSV Bulk Payout Functions ===

async def get_pending_payouts_for_csv() -> List[Dict[str, Any]]:
    """Get all pending payouts with user information for CSV export."""
    payouts = await Payout.find({"status": "pending"}).sort("-created_at").to_list()
    
    csv_data = []
    for payout in payouts:
        # Get user information
        user = await User.get(payout.user_id)
        username = user.username if user else "Unknown User"
        
        csv_row = {
            "payout_id": str(payout.id),
            "user_id": str(payout.user_id),
            "username": username,
            "amount_hc": payout.amount_hc,
            "amount_kwanza": payout.amount_kwanza,
            "payout_method": payout.payout_method,
            "phone_number": payout.phone_number or "",
            "full_name": payout.full_name or "",
            "national_id": payout.national_id or "",
            "bank_iban": payout.bank_iban or "",
            "bank_name": payout.bank_name or "",
            "created_at": payout.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "action": "",  # To be filled by admin
            "admin_notes": "",
            "rejection_reason": ""
        }
        csv_data.append(csv_row)
    
    return csv_data


async def bulk_process_payouts(
    payouts_to_process: List[Dict[str, Any]], 
    admin_username: str
) -> Dict[str, Any]:
    """Process multiple payouts in bulk based on CSV data."""
    results = {
        "processed": 0,
        "failed": 0,
        "errors": [],
        "success_details": []
    }
    
    for payout_data in payouts_to_process:
        try:
            payout_id = PydanticObjectId(payout_data['payout_id'])
            action = payout_data['action'].lower()
            admin_notes = payout_data.get('admin_notes', '')
            rejection_reason = payout_data.get('rejection_reason', '')
            
            # Validate action
            if action not in ['approve', 'reject']:
                results["errors"].append({
                    "payout_id": str(payout_id),
                    "error": f"Invalid action: {action}. Must be 'approve' or 'reject'"
                })
                results["failed"] += 1
                continue
            
            # Validate rejection reason if rejecting
            if action == 'reject' and not rejection_reason.strip():
                results["errors"].append({
                    "payout_id": str(payout_id),
                    "error": "Rejection reason is required when rejecting a payout"
                })
                results["failed"] += 1
                continue
            
            # Process the payout using existing function
            processed_payout = await process_payout(
                payout_id=payout_id,
                admin_username=admin_username,
                action=action,
                admin_notes=admin_notes,
                rejection_reason=rejection_reason
            )
            
            results["processed"] += 1
            results["success_details"].append({
                "payout_id": str(payout_id),
                "action": action,
                "status": processed_payout.status
            })
            
        except HTTPException as e:
            # Check if this is a "already processed" error and handle it differently
            if "already" in str(e.detail).lower():
                results["success_details"].append({
                    "payout_id": str(payout_data.get('payout_id', 'Unknown')),
                    "action": "skipped",
                    "status": f"Already processed: {e.detail}"
                })
                results["processed"] += 1  # Count as processed since it's not an error
            else:
                results["errors"].append({
                    "payout_id": payout_data.get('payout_id', 'Unknown'),
                    "error": e.detail
                })
                results["failed"] += 1
        except Exception as e:
            results["errors"].append({
                "payout_id": payout_data.get('payout_id', 'Unknown'),
                "error": f"Unexpected error: {str(e)}"
            })
            results["failed"] += 1
    
    return results
