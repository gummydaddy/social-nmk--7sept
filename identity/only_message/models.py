from django.db import models
from django.contrib.auth.models import User as AuthUser
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .encryption_utils import serialize_key, generate_key_pair

from cryptography.fernet import Fernet
from django.utils.timezone import now


class LoggedInUser(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='logged_in_user')
    last_activity = models.DateTimeField(default=now)

# session_key = models.CharField(max_length=40, default='')
# session_key = Fernet.generate_key()
# cipher_suite = Fernet(session_key)


@receiver(post_save, sender=AuthUser)
def on_user_login(sender, instance, **kwargs):
    LoggedInUser.objects.get_or_create(user=instance)

@receiver(post_delete, sender=LoggedInUser)
def on_user_logout(sender, instance, **kwargs):
    LoggedInUser.objects.filter(user=instance.user).delete()

class UserEncryptionKeys(models.Model):
    user = models.OneToOneField(AuthUser, on_delete=models.CASCADE, related_name='encryption_keys')
    encryption_public_key = models.TextField()
    encryption_private_key = models.TextField()
    signing_public_key = models.TextField(null=True)
    signing_private_key = models.TextField(null=True)


class ConversationKey(models.Model):
    participants = models.ManyToManyField(AuthUser, related_name='conversations')
    key = models.TextField()

# @receiver(post_save, sender=AuthUser)
# def create_user_encryption_keys(sender, instance, created, **kwargs):
#     if created:
#         key = Fernet.generate_key().decode()
#         UserEncryptionKeys.objects.create(user=instance, public_key=key, private_key=key)

@receiver(post_save, sender=AuthUser)
def create_user_encryption_keys(sender, instance, created, **kwargs):
    if created:
        encryption_private, encryption_public = generate_key_pair()
        signing_private, signing_public = generate_key_pair()
        UserEncryptionKeys.objects.create(
            user=instance,
            encryption_public_key=serialize_key(encryption_public),
            encryption_private_key=serialize_key(encryption_private, is_private=True),
            signing_public_key=serialize_key(signing_public),
            signing_private_key=serialize_key(signing_private, is_private=True)
        )

class Message(models.Model):
    sender = models.ForeignKey(AuthUser, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(AuthUser, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField()  # Encrypted content
    signature = models.TextField(null=True)  # Store the message signature
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.content[:20]}"

