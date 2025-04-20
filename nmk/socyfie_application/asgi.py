"""
ASGI config for nmk project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""
'''
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import service_auth.only_message.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socyfie_application.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            service_auth.only_message.routing.websocket_urlpatterns
        )
    ),
})
'''

import os
import django
from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socyfie_application.settings")
django.setup()  # <-- Important: ensure Django is fully loaded before importing routing

import service_auth.only_message.routing  # now safe to import

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            service_auth.only_message.routing.websocket_urlpatterns
        )
    ),
})

