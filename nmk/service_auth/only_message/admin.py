from django.contrib import admin
from .models import Message, UserEncryptionKeys, ConversationKey

# Register your models here.
admin.site.register(Message),  # Register Group model with the custom admin site
admin.site.register(UserEncryptionKeys),  # Register Group model with the custom admin site
admin.site.register(ConversationKey)  # Register Group model with the custom admin site
