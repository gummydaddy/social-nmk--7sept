import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
#from .models import Message, PreKey, SignedPreKey, IdentityKey
from .models import Message

#from .encryption_utils import encrypt_message, decrypt_message, generate_identity_key_pair, generate_pre_key, generate_signed_pre_key
from .encryption_utils import encrypt_message, decrypt_message, generate_key_pair

#from libsignal.protocol import SignalMessage, PreKeySignalMessage

class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.room_group_name = f"user_{self.user.id}"
            async_to_sync(self.channel_layer.group_add)(
                self.room_group_name,
                self.channel_name
                #"chat", self.channel_name
            )
            self.accept()
        else:
            self.close()

    def disconnect(self, close_code):
        if self.user.is_authenticated:
            async_to_sync(self.channel_layer.group_discard)(
                f"user_{self.user.id}",
                self.channel_name
                #"chat", self.channel_name
            )

    def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'send_message':
            self.handle_send_message(data)

    def handle_send_message(self, data):
        sender = self.user
        recipient_username = data['recipient']
        content = data['content']

        try:
            recipient = User.objects.get(username=recipient_username)
        except User.DoesNotExist:
            self.send(text_data=json.dumps({
                'error': 'Recipient does not exist.'
            }))
            return

        # Encrypt the message
        encrypted_content = encrypt_message(sender, recipient, content)

        # Save the message to the database
        message = Message.objects.create(sender=sender, recipient=recipient, content=encrypted_content)

        # Send the message to the recipient's WebSocket
        async_to_sync(self.channel_layer.group_send)(
            f"user_{recipient.id}",
            {
                'type': 'chat_message',
                'message': encrypted_content,
                'sender': sender.username,
            }
        )

    def chat_message(self, event):
        encrypted_message = event['message']
        sender = event['sender']

        # Decrypt the message content
        decrypted_message = decrypt_message(self.user, sender, encrypted_message)

        self.send(text_data=json.dumps({
            'message': decrypted_message,
            'sender': sender,
        }))


