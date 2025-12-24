# components/notifications.py
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from data.models.models import Notification, User
from core.security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

# --- Pydantic Schemas ---

class NotificationOut(BaseModel):
    id: PydanticObjectId
    title: str
    message: str
    type: str # "payout_status", "system_alert", etc.
    is_read: bool
    metadata: Dict[str, Any] = {}
    created_at: datetime

class UnreadCountOut(BaseModel):
    unread_count: int

# --- Endpoints ---

@router.get("", response_model=List[NotificationOut])
async def get_notifications(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Fetch the current user's notifications.
    Sorted by creation date (newest first).
    """
    notifications = await Notification.find(
        Notification.user_id == current_user.id
    ).sort(-Notification.created_at).skip(offset).limit(limit).to_list()
        
    return notifications


@router.get("/unread-count", response_model=UnreadCountOut)
async def get_unread_count(
    current_user: User = Depends(get_current_user)
):
    """
    Get the total number of unread notifications for the current user.
    Useful for showing badge counts on the UI.
    """
    count = await Notification.find(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_as_read(
    notification_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """
    Mark a specific notification as read.
    """
    notification = await Notification.find_one(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    )
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    notification.is_read = True
    await notification.save()
    
    return notification


@router.patch("/read-all", response_model=dict)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user)
):
    """
    Mark all unread notifications for the current user as read.
    """
    await Notification.find(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"$set": {"is_read": True}})
    
    return {"message": "All notifications marked as read"}
