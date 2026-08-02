import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.html import strip_tags

from .models import Notification

logger = logging.getLogger(__name__)

# emoji / label per notification type — extend as needed
NOTIF_META = {
    'follow':  ('👋', 'New follower'),
    'like':    ('❤️', 'New like'),
    'comment': ('💬', 'New comment'),
    'tag':     ('🏷️', 'You were tagged'),
}


@receiver(post_save, sender=Notification)
def dispatch_notion_notification(sender, instance, created, **kwargs):
    """
    Fires whenever a Notification row is created anywhere in the notion app
    (like_notion, post_comment tags, post_notion tags, etc.) and relays it
    through the same WebSocket + Web Push pipeline used by only_message.
    """
    if not created or not instance.user_id:
        return

    # Don't notify someone about their own action
    if instance.related_user_id and instance.related_user_id == instance.user_id:
        return

    try:
        # Local import avoids any import-order issues between apps
        from service_auth.only_message.websocket_notifications import send_notification_sync

        notif_type = instance.type or 'activity'
        emoji, label = NOTIF_META.get(notif_type, ('🔔', 'Socyfie'))

        actor_username = None
        if instance.related_user_id:
            actor_username = instance.related_user.username
        elif instance.liked_by_id:
            actor_username = instance.liked_by.username

        # Build a safe target URL
        url = '/notifications/'
        if instance.related_notion_id:
            try:
                url = instance.related_notion.get_absolute_url()
            except Exception:
                pass

        notification_data = {
            'id':              f'notion_{instance.id}',
            'type':            'notion_notification',   # new push-worthy type
            'notion_type':     notif_type,               # 'like' / 'comment' / 'follow' / 'tag'
            'sender':          actor_username or 'Socyfie',
            'title':           f'{emoji} {label}',
            'message':         strip_tags(instance.content or '')[:150],
            'url':             url,
            'notification_id': instance.id,
            'timestamp':       instance.created_at.timestamp() if instance.created_at else None,
        }

        send_notification_sync(instance.user_id, notification_data)
        logger.info(
            f"🔔 Dispatched '{notif_type}' notion notification {instance.id} "
            f"to user {instance.user_id}"
        )

    except Exception as e:
        logger.error(
            f"Failed to dispatch notion notification {instance.id}: {e}",
            exc_info=True
        )
