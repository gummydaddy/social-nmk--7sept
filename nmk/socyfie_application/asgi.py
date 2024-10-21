"""
ASGI config for nmk project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import service_auth.only_message.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "service_auth.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            service_auth.only_message.routing.websocket_urlpatterns
        )
    ),
})
