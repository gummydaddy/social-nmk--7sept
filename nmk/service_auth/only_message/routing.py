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
from django.urls import re_path
from django.urls import path
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from . import consumers
from .consumers import ChatConsumer
from .notification_consumer import NotificationConsumer

# Just export the websocket_urlpatterns
websocket_urlpatterns = [
    #path("ws/chat/", ChatConsumer.as_asgi()),
    #re_path(r'ws/chat/(?P<username>\w+)/$', ChatConsumer.as_asgi()),

    re_path(r'ws/chat/(?P<username>[\w.@+-]+)/$', ChatConsumer.as_asgi()),

    # Notification WebSocket (for push notifications)
    path('ws/notifications/', NotificationConsumer.as_asgi()),

    #re_path(r'ws/chat/(?P<username>\w+)/$', consumers.ChatConsumer.as_asgi()),
    #added this modification to the routing after making updates to the cousumer.py using with modified user_message_view and updated user_message.html
    #re_path(r'ws/chat/(?P<username>\w+)/$', ChatConsumer.as_asgi()),
    #re_path(r'ws/chat/(?P<username>[\w.@+-]+)/$', ChatConsumer.as_asgi()),

]

