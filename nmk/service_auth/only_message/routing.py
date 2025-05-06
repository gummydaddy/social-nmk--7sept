# routing.py
'''
from django.core.asgi import get_asgi_application
from django.urls import path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from . import consumers
from .consumers import ChatConsumer

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([
                path("ws/chat/", consumers.ChatConsumer.as_asgi()),
            ])
        )
    ),
})
'''

# service_auth/only_message/routing.py

from django.urls import path
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from .consumers import ChatConsumer

# Just export the websocket_urlpatterns
websocket_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
]

