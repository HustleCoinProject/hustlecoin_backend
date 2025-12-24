# Notification System Integration Guide

This document describes how to integrate the new notification system into the frontend.

## Overview
The system allows users to receive internal app notifications (e.g., when a payout is approved or rejected). These notifications are stored in MongoDB and fetched via HTTP endpoints.

## Data Model

A `Notification` object has the following structure:

```json
{
  "_id": "651234567890abcdef123456",
  "title": "Payout Approved! 🎉",
  "message": "Your payout of 2,000 Kz has been approved.",
  "type": "payout_status",
  "is_read": false,
  "metadata": {
    "payout_id": "650000000000abcdef123456"
  },
  "created_at": "2023-10-25T14:30:00.000Z"
}
```

### Notification Types
- `payout_status`: Triggered when admin approves or rejects a payout.
- `system_alert`: General system messages.

## API Endpoints

### 1. Fetch Notifications
**GET** `/api/notifications`

**Query Parameters:**
- `limit` (int, default: 20)
- `offset` (int, default: 0)

**Response:**
Returns a list of notification objects.

### 2. Get Unread Count
**GET** `/api/notifications/unread-count`

**Response:**
```json
{
  "unread_count": 5
}
```
Use this to show a red badge/dot on the notification icon.

### 3. Mark as Read
**PATCH** `/api/notifications/{notification_id}/read`

**Response:**
Returns the updated notification object.

### 4. Mark All as Read
**PATCH** `/api/notifications/read-all`

**Response:**
```json
{
  "message": "All notifications marked as read"
}
```

## Integration Flow

1.  **Polling/Fetching**:
    - Call `/api/notifications/unread-count` periodically (e.g., every 60s) or on app resume to update the badge.
    - Call `/api/notifications` when the user opens the notification screen.

2.  **User Action**:
    - When user taps a notification, you might want to mark it as read immediately using `PATCH /api/notifications/{id}/read`.
    - Or provide a "Mark all as read" button using `PATCH /api/notifications/read-all`.

3.  **Navigation**:
    - Use the `metadata` field to navigate. For example, if `type` is `payout_status`, checking `metadata.payout_id` could allow navigating to the transaction history details.
