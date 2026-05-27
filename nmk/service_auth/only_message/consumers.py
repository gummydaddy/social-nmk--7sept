import json
import base64
from django.core.files.base import ContentFile

from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync, sync_to_async

from django.contrib.auth import get_user_model

from django.contrib.auth.models import User

from .models import Message, UserEncryptionKeys, ConversationKey

from .encryption_utils import encrypt_message, decrypt_message, generate_key_pair, sign_message, verify_message

from cryptography.fernet import Fernet

from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q

import logging

#from libsignal.protocol import SignalMessage, PreKeySignalMessage



logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope["user"]
        
        # Get username from URL kwargs
        self.other_username = self.scope['url_route']['kwargs'].get('username')
        
        logger.info(f"WebSocket connection attempt: user={self.user}, other_username={self.other_username}")
        
        if not self.user.is_authenticated:
            logger.warning("Unauthenticated user tried to connect to WebSocket")
            await self.close()
            return
        
        if not self.other_username:
            logger.error("No username in URL kwargs")
            await self.close()
            return
        
        try:
            self.other_user = await sync_to_async(User.objects.get)(username=self.other_username)
        except User.DoesNotExist:
            logger.error(f"User {self.other_username} does not exist")
            await self.close()
            return
        
        # Create unique room group name based on both user IDs (sorted to ensure consistency)
        sorted_ids = sorted([self.user.id, self.other_user.id])
        self.room_group_name = f'chat_{sorted_ids[0]}_{sorted_ids[1]}'
        
        logger.info(f"User {self.user.username} joining room: {self.room_group_name}")
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"✓ WebSocket CONNECTED: {self.user.username} <-> {self.other_username} (room: {self.room_group_name})")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'room_group_name'):
            logger.info(f"User {self.user.username} leaving room: {self.room_group_name}")
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"✗ WebSocket DISCONNECTED: {self.user.username} (code: {close_code})")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            logger.info(f"Received WebSocket message: type={message_type}, from={self.user.username}")
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)

    async def handle_chat_message(self, data):
        """
        Handle chat message - BROADCAST ONLY, do not save to database
        (Database save happens in views.py)
        """
        content = data.get('content', '').strip()
        file_url = data.get('file_url')
        message_id = data.get('message_id')  # Get message_id from views.py
        timestamp = data.get('timestamp')
        
        logger.info(f"Broadcasting message: content={bool(content)}, file={bool(file_url)}, msg_id={message_id}")
        
        if not content and not file_url:
            logger.warning("Empty message received")
            return
        
        # IMPORTANT: Do NOT save to database here - it's already saved in views.py
        # Just broadcast to all users in the room
        
        broadcast_data = {
            'type': 'chat_message_broadcast',
            'message_id': message_id,
            'content': content,
            'sender': self.user.username,
            'sender_id': self.user.id,
            'timestamp': timestamp,
            'signature_valid': True,
            'file_url': file_url
        }
        
        logger.info(f"Broadcasting message to room: {self.room_group_name}")
        
        await self.channel_layer.group_send(
            self.room_group_name,
            broadcast_data
        )
        
        logger.info(f"✓ Message broadcast successful (msg_id={message_id})")

    async def chat_message_broadcast(self, event):
        """Handle message broadcast from group - send to WebSocket"""
        logger.info(f"Sending broadcast to {self.user.username}: msg_id={event.get('message_id')}")
        
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event.get('message_id'),
            'content': event.get('content'),
            'sender': event.get('sender'),
            'sender_id': event.get('sender_id'),
            'timestamp': event.get('timestamp'),
            'signature_valid': event.get('signature_valid'),
            'file_url': event.get('file_url')
        }))
        
        logger.info(f"✓ Broadcast sent to {self.user.username}")




    async def file_status_update(self, event):
        """Handle file upload status updates from Celery tasks"""
        logger.info(f"Sending file status update to {self.user.username}: msg_id={event.get('message_id')}")
        
        await self.send(text_data=json.dumps({
            'type': 'file_status',
            'message_id': event.get('message_id'),
            'status': event.get('status'),
            'progress': event.get('progress'),
            'message': event.get('message'),
            'file_url': event.get('file_url'),
            'file_name': event.get('file_name'),
            'file_size': event.get('file_size')
        }))
        
        logger.info(f"✓ File status update sent to {self.user.username}")
 
    async def send_push_notification_to_recipient(self, message_id):
        """Send push notification to recipient if they're not active"""
        try:
            # Import here to avoid circular imports
            from .push_utils import send_message_notification
            
            # Get the message from database
            message = await sync_to_async(Message.objects.get)(id=message_id)
            
            # Send push notification
            logger.info(f"Sending push notification for message {message_id}")
            await sync_to_async(send_message_notification)(message)
            
        except Message.DoesNotExist:
            logger.error(f"Message {message_id} not found for push notification")
        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}", exc_info=True)




    async def chat_message_delete(self, event):
        """
        Handle deleted messages broadcast
        """
        logger.info(
            f"Sending delete event to {self.user.username}: "
            f"message_ids={event.get('message_ids')}"
        )

        await self.send(text_data=json.dumps({
            'type': 'message_delete',
            'message_ids': event.get('message_ids', []),
            'sender': event.get('sender')
        }))

        logger.info(
            f"✓ Delete broadcast sent to {self.user.username}"
        )
