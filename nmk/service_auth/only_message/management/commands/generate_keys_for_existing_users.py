
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from only_message.models import UserEncryptionKeys
from only_message.encryption_utils import generate_key_pair, serialize_key


class Command(BaseCommand):
    help = 'Generate encryption and signing keys for existing users without them'

    def handle(self, *args, **kwargs):
        users = User.objects.all()
        for user in users:
            if not UserEncryptionKeys.objects.filter(user=user).exists():
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
            else:
                self.stdout.write(self.style.WARNING(f'Keys already exist for user: {user.username}'))
