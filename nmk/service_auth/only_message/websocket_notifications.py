'''
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

#latest
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




#old
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

'''




# nmk/service_auth/only_message/websocket_notifications.py
#
# WebSocket notification system + Web Push bridge.
#
# KEY CHANGE from the previous version:
#   Web Push is now dispatched via Celery (.delay()), which is a sub-
#   millisecond Redis write.  pywebpush's HTTP call to the push service
#   happens inside a Celery worker — completely off the critical path.
#
#   This means the WebSocket broadcast (in-app) is NEVER blocked by the
#   push HTTP request, restoring Android in-app notifications.

import logging
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Notification storage  (Django cache / Redis, unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def store_notification(user_id, notification_data):
    cache_key     = f"notifications:{user_id}"
    notifications = cache.get(cache_key, [])
    notification_data["created_at"] = time.time()
    notifications.append(notification_data)
    if len(notifications) > 50:
        notifications = notifications[-50:]
    cache.set(cache_key, notifications, timeout=604800)
    logger.info("✅ Stored notification for user %s: %s",
                user_id, notification_data.get("type"))
    return True


def get_notifications(user_id, limit=20):
    return cache.get(f"notifications:{user_id}", [])[-limit:]


def get_unread_count(user_id):
    return cache.get(f"notifications_unread:{user_id}", 0)


def increment_unread_count(user_id):
    cache_key = f"notifications_unread:{user_id}"
    count     = cache.get(cache_key, 0) + 1
    cache.set(cache_key, count, timeout=604800)
    logger.info("📊 Unread count for user %s: %s", user_id, count)
    return count


def clear_unread_count(user_id):
    cache.delete(f"notifications_unread:{user_id}")
    return True


def mark_notification_read(user_id, notification_id):
    cache_key     = f"notifications:{user_id}"
    notifications = cache.get(cache_key, [])
    for n in notifications:
        if n.get("id") == notification_id:
            n["read"] = True
    cache.set(cache_key, notifications, timeout=604800)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Notification creation  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def create_message_notification(sender_username, sender_id,
                                recipient_user_id, message_preview,
                                message_id=None):
    notification_id = f"msg_{message_id}_{int(time.time() * 1000)}"
    notification_data = {
        "id"        : notification_id,
        "type"      : "new_message",
        "sender"    : sender_username,
        "sender_id" : sender_id,
        "message"   : message_preview[:100],
        "timestamp" : time.time(),
        "read"      : False,
        "url"       : f"/user_messages_view/{sender_username}/",
        "message_id": message_id,
    }
    store_notification(recipient_user_id, notification_data)
    unread_count = increment_unread_count(recipient_user_id)
    notification_data["unread_count"] = unread_count
    logger.info("🔔 Created message notification: %s → user %s",
                sender_username, recipient_user_id)
    return notification_data


def create_typing_notification(sender_username, recipient_user_id):
    return {"type": "typing_indicator", "sender": sender_username,
            "timestamp": time.time()}


# ─────────────────────────────────────────────────────────────────────────────
# _dispatch_push  — shared helper used by both sync and async paths
# ─────────────────────────────────────────────────────────────────────────────

def _dispatch_push(recipient_user_id, notification_data):
    """
    Queue a Celery task to send Web Push.

    .delay() is a Redis write (< 1 ms) — never blocks anything.
    The actual pywebpush HTTP call runs in a Celery worker process.
    """
    try:
        # Import here so the module loads even if Celery isn't configured
        from .tasks import send_web_push_task
        send_web_push_task.delay(recipient_user_id, notification_data)
        logger.debug("📲 Web Push queued for user %s (type=%s)",
                     recipient_user_id, notification_data.get("type"))
    except Exception as exc:
        # Non-critical — WS notification already delivered if app was open
        logger.warning("⚠️ Could not queue Web Push for user %s: %s",
                       recipient_user_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket broadcast  (async — used by NotificationConsumer)
# ─────────────────────────────────────────────────────────────────────────────

async def send_notification_via_websocket(recipient_user_id, notification_data):
    """
    Send notification via WebSocket (immediate, in-app).
    Also queues a Celery task for Web Push (offline delivery).

    The WS path is unaffected by push latency — .delay() returns in < 1 ms.
    """
    from channels.layers import get_channel_layer

    # ── 1. WebSocket  (critical path — must stay fast) ───────────────────────
    try:
        channel_layer = get_channel_layer()
        group_name    = f"notifications_{recipient_user_id}"
        logger.info("📡 WS notification → %s", group_name)
        await channel_layer.group_send(
            group_name,
            {"type": "notification_message", "notification": notification_data},
        )
        logger.info("✅ WS notification delivered to user %s", recipient_user_id)
    except Exception as exc:
        logger.error("❌ WS broadcast failed for user %s: %s",
                     recipient_user_id, exc, exc_info=True)

    # ── 2. Web Push  (non-blocking — Celery task) ────────────────────────────
    # We must call _dispatch_push from a sync context.
    # sync_to_async with thread_sensitive=False uses a real thread pool
    # and returns immediately once the Celery .delay() Redis write finishes.
    try:
        from asgiref.sync import sync_to_async
        await sync_to_async(_dispatch_push, thread_sensitive=False)(
            recipient_user_id, notification_data
        )
    except Exception as exc:
        logger.warning("⚠️ Push dispatch failed (non-critical): %s", exc)

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Synchronous broadcast  (used from Django views)
# ─────────────────────────────────────────────────────────────────────────────

def send_notification_sync(recipient_user_id, notification_data):
    """
    Sync version — call this from regular Django views.

    WebSocket broadcast + Celery push task dispatch.
    Total added latency: < 2 ms (two Redis writes).
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    # ── 1. WebSocket  (critical path) ────────────────────────────────────────
    try:
        channel_layer = get_channel_layer()
        group_name    = f"notifications_{recipient_user_id}"
        logger.info("📡 WS notification (sync) → %s", group_name)
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "notification_message", "notification": notification_data},
        )
        logger.info("✅ WS notification delivered to user %s", recipient_user_id)
    except Exception as exc:
        logger.error("❌ WS broadcast failed for user %s: %s",
                     recipient_user_id, exc, exc_info=True)

    # ── 2. Web Push  (non-blocking — Celery task) ────────────────────────────
    _dispatch_push(recipient_user_id, notification_data)

    return True



