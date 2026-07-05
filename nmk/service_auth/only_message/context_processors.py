"""
nmk/service_auth/only_message/context_processors.py

Injects VAPID_PUBLIC_KEY into every template context so
push_notification_init.html can read it without a dedicated API call.
"""

from django.conf import settings


def push_config(request):
    return {
        "VAPID_PUBLIC_KEY": getattr(settings, "VAPID_PUBLIC_KEY", ""),
    }
