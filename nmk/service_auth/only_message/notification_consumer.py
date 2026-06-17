# nmk/service_auth/only_message/notification_consumer.py
# Create this NEW file for notification WebSocket handling

import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging
from asgiref.sync import sync_to_async

from .websocket_notifications import send_notification_via_websocket

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Connect user to their personal notification channel"""
        self.user = self.scope["user"]
        
        if not self.user.is_authenticated:
            logger.warning("Unauthenticated user tried to connect to notifications")
            await self.close()
            return
        
        # Create personal notification group for this user
        self.notification_group_name = f'notifications_{self.user.id}'
        
        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"✅ Notification WebSocket CONNECTED: user={self.user.username}, group={self.notification_group_name}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to notification service',
            'user_id': self.user.id,
            'username': self.user.username
        }))

    async def disconnect(self, close_code):
        """Disconnect from notification channel"""
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )
            logger.info(f"❌ Notification WebSocket DISCONNECTED: user={self.user.username}, code={close_code}")

 
    # ──────────────────────────────────────────────────────────────────────────
    # Incoming messages from the browser
    # ──────────────────────────────────────────────────────────────────────────
 
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
 
        msg_type = data.get('type', '')
        logger.info(f'Notification WS ← {msg_type} from {self.user.username}')
 
        handlers = {
            'ping':          self._ping,
            'mark_read':     self._mark_read,
            # ── call signalling ──────────────────────────────────────────────
            'call_initiate': self._call_initiate,
            'call_answer':   self._call_answer,
            'call_reject':   self._call_reject,
            'call_end':      self._call_end,
            'ice_candidate': self._ice_candidate,
            'call_busy':     self._call_busy,
        }
        handler = handlers.get(msg_type)
        if handler:
            await handler(data)
 
    # ── generic handlers ──────────────────────────────────────────────────────
 
    async def _ping(self, _):
        await self.send(text_data=json.dumps({'type': 'pong'}))
 
    async def _mark_read(self, _):
        await self.send(text_data=json.dumps({'type': 'marked_read', 'success': True}))
 
    # ── call signalling handlers ──────────────────────────────────────────────
    #
    # Each handler receives a signal from the caller's browser, builds the
    # notification payload, and relays it to the other user's personal channel
    # using send_notification_via_websocket().
    #
    # The browser must always include the target user's id so we know where
    # to send:
    #   call_initiate  → recipient_id
    #   call_answer    → caller_id
    #   call_reject    → caller_id
    #   call_end       → peer_id
    #   ice_candidate  → peer_id
    #   call_busy      → caller_id

    async def _call_initiate(self, data):
        recipient_id = data.get('recipient_id')
        if not recipient_id:
            logger.warning('call_initiate: missing recipient_id')
            return

        caller_pic = data.get('caller_pic') or await _get_pic(self.user)
        call_type = data.get('call_type', 'audio')

        logger.info(f'📞 call_initiate ({call_type}): {self.user.username} → user {recipient_id}')

        await send_notification_via_websocket(recipient_id, {
            'type':       'incoming_call',
            'caller':     self.user.username,
            'caller_id':  self.user.id,
            'caller_pic': caller_pic,
            'offer':      data.get('offer'),
            'call_type':  call_type,
            'chat_url':   f'/message/user_messages_view/{self.user.username}/',
        })

    async def _call_answer(self, data):
        caller_id = data.get('caller_id')
        if not caller_id:
            return
        logger.info(f'✅ call_answer: {self.user.username} → user {caller_id}')

        await send_notification_via_websocket(caller_id, {
            'type':        'call_answered',
            'answerer':    self.user.username,
            'answerer_id': self.user.id,
            'answer':      data.get('answer'),
            'call_type':   data.get('call_type', 'audio'),
        })

    async def _call_reject(self, data):
        caller_id = data.get('caller_id')
        if not caller_id:
            return
        logger.info(f'❌ call_reject: {self.user.username} → user {caller_id}')

        await send_notification_via_websocket(caller_id, {
            'type':      'call_rejected',
            'rejector':  self.user.username,
            'call_type': data.get('call_type', 'audio'),
        })

    async def _call_end(self, data):
        peer_id = data.get('peer_id')
        if not peer_id:
            return
        logger.info(f'📵 call_end: {self.user.username} → user {peer_id}')

        await send_notification_via_websocket(peer_id, {
            'type':      'call_ended',
            'ender':     self.user.username,
            'call_type': data.get('call_type', 'audio'),
        })

    async def _ice_candidate(self, data):
        peer_id = data.get('peer_id')
        if not peer_id:
            return

        await send_notification_via_websocket(peer_id, {
            'type':      'ice_candidate',
            'candidate': data.get('candidate'),
            'sender_id': self.user.id,
            'sender':    self.user.username,
            'call_type': data.get('call_type', 'audio'),
        })

    async def _call_busy(self, data):
        caller_id = data.get('caller_id')
        if not caller_id:
            return

        await send_notification_via_websocket(caller_id, {
            'type':      'call_busy',
            'from_user': self.user.username,
            'call_type': data.get('call_type', 'audio'),
        })



 
    # ──────────────────────────────────────────────────────────────────────────
    # Channel-layer → WebSocket forwarder
    # (server pushes a notification_message event → browser receives it)
    # ──────────────────────────────────────────────────────────────────────────
    async def notification_message(self, event):
        """
        Handle notification broadcast from channel layer
        This is called when send_notification_sync broadcasts to the group
        """
        notification_data = event['notification']
        #notification = event.get('notification', {})

        logger.info(f"🔔 Sending notification to {self.user.username}: {notification_data.get('type')}")
        
        # Send notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': notification_data
        }))
        
        logger.info(f"✅ Notification sent to {self.user.username}")



# ── module-level helper (keeps the consumer class clean) ─────────────────────
 
@sync_to_async
def _get_pic(user):
    """Safely return the user's profile picture URL, or empty string."""
    try:
        pic = user.profile.profile_picture
        return pic.url if pic else ''
    except Exception:
        return ''
