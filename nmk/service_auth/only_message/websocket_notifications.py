# nmk/service_auth/only_message/websocket_notifications.py
# Complete WebSocket-based notification system
# NO FCM, NO new models/migrations needed

import logging
from django.core.cache import cache
from django.contrib.auth.models import User
import json
import time

logger = logging.getLogger(__name__)

# ========================================
# NOTIFICATION STORAGE (Using Django Cache)
# ========================================

def store_notification(user_id, notification_data):
    """
    Store notification in cache for a user
    
    Args:
        user_id: User ID to send notification to
        notification_data: Dict with notification details
    """
    cache_key = f'notifications:{user_id}'
    notifications = cache.get(cache_key, [])
    
    # Add new notification with timestamp
    notification_data['created_at'] = time.time()
    notifications.append(notification_data)
    
    # Keep only last 50 notifications
    if len(notifications) > 50:
        notifications = notifications[-50:]
    
    # Store in cache (expires in 7 days)
    cache.set(cache_key, notifications, timeout=604800)
    
    logger.info(f"✅ Stored notification for user {user_id}: {notification_data.get('type')}")
    return True


def get_notifications(user_id, limit=20):
    """Get notifications for a user"""
    cache_key = f'notifications:{user_id}'
    notifications = cache.get(cache_key, [])
    return notifications[-limit:]  # Return most recent


def get_unread_count(user_id):
    """Get count of unread notifications"""
    cache_key = f'notifications_unread:{user_id}'
    count = cache.get(cache_key, 0)
    return count


def increment_unread_count(user_id):
    """Increment unread notification count"""
    cache_key = f'notifications_unread:{user_id}'
    current = cache.get(cache_key, 0)
    new_count = current + 1
    cache.set(cache_key, new_count, timeout=604800)
    logger.info(f"📊 Unread count for user {user_id}: {new_count}")
    return new_count


def clear_unread_count(user_id):
    """Clear unread notification count"""
    cache_key = f'notifications_unread:{user_id}'
    cache.delete(cache_key)
    logger.info(f"✅ Cleared unread count for user {user_id}")
    return True


def mark_notification_read(user_id, notification_id):
    """Mark a specific notification as read"""
    cache_key = f'notifications:{user_id}'
    notifications = cache.get(cache_key, [])
    
    for notif in notifications:
        if notif.get('id') == notification_id:
            notif['read'] = True
            logger.info(f"✅ Marked notification {notification_id} as read for user {user_id}")
    
    cache.set(cache_key, notifications, timeout=604800)
    return True


# ========================================
# NOTIFICATION CREATION
# ========================================

def create_message_notification(sender_username, sender_id, recipient_user_id, message_preview, message_id=None):
    """
    Create a message notification
    
    Args:
        sender_username: Username of sender
        sender_id: User ID of sender
        recipient_user_id: User ID of recipient
        message_preview: Preview of message (first 100 chars)
        message_id: Optional message ID
    
    Returns:
        notification_data dict ready for WebSocket broadcast
    """
    notification_id = f'msg_{message_id}_{int(time.time() * 1000)}'
    
    notification_data = {
        'id': notification_id,
        'type': 'new_message',
        'sender': sender_username,
        'sender_id': sender_id,
        'message': message_preview[:100],
        'timestamp': time.time(),
        'read': False,
        'url': f'/user_messages_view/{sender_username}/',
        'message_id': message_id
    }
    
    # Store in cache
    store_notification(recipient_user_id, notification_data)
    
    # Increment unread count
    unread_count = increment_unread_count(recipient_user_id)
    
    # Add unread count to notification
    notification_data['unread_count'] = unread_count
    
    logger.info(f"🔔 Created message notification: {sender_username} -> user_id {recipient_user_id}")
    
    return notification_data


def create_typing_notification(sender_username, recipient_user_id):
    """
    Create typing indicator notification (not stored, just broadcast)
    """
    notification_data = {
        'type': 'typing_indicator',
        'sender': sender_username,
        'timestamp': time.time()
    }
    
    logger.info(f"⌨️ Typing notification: {sender_username} -> user {recipient_user_id}")
    return notification_data


# ========================================
# WEBSOCKET NOTIFICATION BROADCAST
# ========================================

async def send_notification_via_websocket(recipient_user_id, notification_data):
    """
    Send notification to user via WebSocket
    Uses Django Channels to broadcast to user's notification channel
    
    Args:
        recipient_user_id: User ID to send notification to
        notification_data: Notification data dict
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    try:
        channel_layer = get_channel_layer()
        
        # Send to user's personal notification channel
        group_name = f'notifications_{recipient_user_id}'
        
        logger.info(f"📡 Broadcasting notification to group: {group_name}")
        
        await channel_layer.group_send(
            group_name,
            {
                'type': 'notification_message',
                'notification': notification_data
            }
        )
        
        logger.info(f"✅ Notification broadcast successful to user {recipient_user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error broadcasting notification: {str(e)}", exc_info=True)
        return False


def send_notification_sync(recipient_user_id, notification_data):
    """
    Synchronous version of send_notification_via_websocket
    Use this in Django views (synchronous context)
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    try:
        channel_layer = get_channel_layer()
        group_name = f'notifications_{recipient_user_id}'
        
        logger.info(f"📡 Broadcasting notification (sync) to group: {group_name}")
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'notification_message',
                'notification': notification_data
            }
        )
        
        logger.info(f"✅ Notification broadcast successful to user {recipient_user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error broadcasting notification: {str(e)}", exc_info=True)
        return False
