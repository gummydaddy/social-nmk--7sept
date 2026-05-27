# nmk/service_auth/only_message/notification_consumer.py
# Create this NEW file for notification WebSocket handling

import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

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

    async def receive(self, text_data):
        """Handle messages from client (e.g., mark as read)"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            logger.info(f"📨 Received from client: {message_type}")
            
            if message_type == 'mark_read':
                # Handle marking notifications as read
                await self.send(text_data=json.dumps({
                    'type': 'marked_read',
                    'success': True
                }))
                
            elif message_type == 'ping':
                # Respond to ping to keep connection alive
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from client: {e}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}", exc_info=True)

    async def notification_message(self, event):
        """
        Handle notification broadcast from channel layer
        This is called when send_notification_sync broadcasts to the group
        """
        notification_data = event['notification']
        
        logger.info(f"🔔 Sending notification to {self.user.username}: {notification_data.get('type')}")
        
        # Send notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': notification_data
        }))
        
        logger.info(f"✅ Notification sent to {self.user.username}")
