from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from only_message.models import UserEncryptionKeys, Message
from only_message.encryption_utils import encrypt_message, decrypt_message, generate_key_pair, serialize_key

class Command(BaseCommand):
    help = 'Regenerate encryption and signing keys for all users and re-encrypt existing messages'

    def handle(self, *args, **kwargs):
        users = User.objects.all()
        for user in users:
            try:
                keys = UserEncryptionKeys.objects.get(user=user)
                
                # Log old keys before deletion (optional, for backup/debugging purposes)
                self.stdout.write(f'Old encryption keys for user {user.username}: {keys.encryption_private_key}, {keys.encryption_public_key}')
                self.stdout.write(f'Old signing keys for user {user.username}: {keys.signing_private_key}, {keys.signing_public_key}')
                
                # Store old keys for decryption
                old_encryption_private_key = keys.encryption_private_key
                old_encryption_public_key = keys.encryption_public_key
                
                # Generate new keys
                encryption_private, encryption_public = generate_key_pair()
                signing_private, signing_public = generate_key_pair()
                
                # Update keys
                keys.encryption_public_key = serialize_key(encryption_public)
                keys.encryption_private_key = serialize_key(encryption_private, is_private=True)
                keys.signing_public_key = serialize_key(signing_public)
                keys.signing_private_key = serialize_key(signing_private, is_private=True)
                keys.save()
                
                # Re-encrypt existing messages
                messages = Message.objects.filter(sender=user) | Message.objects.filter(recipient=user)
                for message in messages:
                    # Decrypt the message using the old key
                    decrypted_content = decrypt_message(message.content, old_encryption_private_key.encode())
                    if decrypted_content:
                        # Encrypt the message using the new key
                        new_encrypted_content = encrypt_message(decrypted_content, keys.encryption_public_key.encode())
                        message.content = new_encrypted_content
                        message.save()
                    else:
                        self.stdout.write(self.style.WARNING(f'Failed to decrypt message {message.id} for user {user.username}'))
                
                self.stdout.write(self.style.SUCCESS(f'Regenerated keys and re-encrypted messages for user: {user.username}'))
            except UserEncryptionKeys.DoesNotExist:
                # Generate new keys if no existing keys found
                encryption_private, encryption_public = generate_key_pair()
                signing_private, signing_public = generate_key_pair()
                
                UserEncryptionKeys.objects.create(
                    user=user,
                    encryption_public_key=serialize_key(encryption_public),
                    encryption_private_key=serialize_key(encryption_private, is_private=True),
                    signing_public_key=serialize_key(signing_public),
                    signing_private_key=serialize_key(signing_private, is_private=True)
                )
                self.stdout.write(self.style.SUCCESS(f'Generated keys for user: {user.username}'))
