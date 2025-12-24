# data/models/__init__.py
# Export all models for easy importing

from .models import User, InventoryItem, Quiz, LandTile, Payout, SystemSettings, Notification

__all__ = ["User", "InventoryItem", "Quiz", "LandTile", "Payout", "SystemSettings", "Notification"]