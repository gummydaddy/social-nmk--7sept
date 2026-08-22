"""
nmk/service_auth/only_message/push_notifications.py  — REPLACE previous version.

Key change: _get_vapid_config() now accepts VAPID_PRIVATE_KEY as either:
  • A 43-char base64url string  (new default from generate_vapid_keys)
  • A PEM string                (backward compatible)

When given a base64url key, the function reconstructs a correctly-formatted
PEM string programmatically, so OpenSSL never sees a malformed "header too long"
PEM regardless of how the key was stored in settings.py.
"""

import json
import logging

from django.conf import settings
from django_redis import get_redis_connection
from django.urls import reverse

logger = logging.getLogger(__name__)

_PREFIX    = "push:subs:"
_TTL       = 60 * 60 * 24 * 90   # 90 days

PUSH_WORTHY = {"new_message", "incoming_call", "notion_notification", "group_message"}


# ─────────────────────────────────────────────────────────────────────────────
# Subscription CRUD (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def save_push_subscription(user_id: int, subscription_info: dict) -> bool:
    endpoint = (subscription_info or {}).get("endpoint", "")
    if not endpoint:
        logger.warning("save_push_subscription: no endpoint for user %s", user_id)
        return False
    try:
        r   = get_redis_connection("default")
        key = f"{_PREFIX}{user_id}"
        r.hset(key, endpoint, json.dumps(subscription_info))
        r.expire(key, _TTL)
        logger.info("✅ Push subscription saved for user %s", user_id)
        return True
    except Exception as exc:
        logger.error("save_push_subscription error: %s", exc)
        return False


def delete_push_subscription(user_id: int, endpoint: str) -> bool:
    try:
        r = get_redis_connection("default")
        r.hdel(f"{_PREFIX}{user_id}", endpoint)
        logger.info("Push subscription removed for user %s", user_id)
        return True
    except Exception as exc:
        logger.error("delete_push_subscription error: %s", exc)
        return False


def get_push_subscriptions(user_id: int) -> list:
    try:
        r   = get_redis_connection("default")
        raw = r.hgetall(f"{_PREFIX}{user_id}")
        subs = []
        for _ep, blob in raw.items():
            try:
                if isinstance(blob, bytes):
                    blob = blob.decode("utf-8")
                subs.append(json.loads(blob))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return subs
    except Exception as exc:
        logger.error("get_push_subscriptions error: %s", exc)
        return []


def delete_all_push_subscriptions(user_id: int) -> bool:
    try:
        get_redis_connection("default").delete(f"{_PREFIX}{user_id}")
        return True
    except Exception as exc:
        logger.error("delete_all_push_subscriptions error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# VAPID config — handles both base64url and PEM formats
# ─────────────────────────────────────────────────────────────────────────────

def _base64url_to_pem(b64url: str) -> str:
    """
    Convert a base64url-encoded 32-byte EC private scalar to a properly
    formatted PEM string.

    This is the inverse of:
        raw = private_key.private_numbers().private_value.to_bytes(32, 'big')
        b64 = base64.urlsafe_b64encode(raw).decode().rstrip('=')

    The reconstructed PEM has correct 64-char line wrapping so OpenSSL never
    raises "header too long" regardless of how the b64url string was stored.
    """
    import base64 as _b64
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    # Restore padding, decode to 32 raw bytes
    padding = "=" * ((4 - len(b64url) % 4) % 4)
    raw     = _b64.urlsafe_b64decode(b64url + padding)

    if len(raw) != 32:
        raise ValueError(
            f"Expected 32 bytes for EC P-256 private scalar, got {len(raw)}"
        )

    # Reconstruct the full EC private key object
    private_int = int.from_bytes(raw, "big")
    ec_key      = ec.derive_private_key(private_int, ec.SECP256R1(), default_backend())

    # Export as correctly-formatted PEM (cryptography always writes proper 64-char lines)
    return ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _get_vapid_config():
    """
    Return (pem_private_key_str, vapid_claims) or (None, None).

    Accepts VAPID_PRIVATE_KEY in two formats:
      1. base64url string  — 43 chars, no newlines, output of generate_vapid_keys
      2. PEM string        — backward compatible with old generate_vapid_keys output

    In both cases the returned private key is a correctly-formatted PEM string
    ready to pass directly to pywebpush.webpush().
    """
    #raw_key = getattr(settings, "VAPID_PRIVATE_KEY", "").strip()
    #claims  = getattr(settings, "VAPID_CLAIMS",      {})

    raw_key = settings.VAPID_PRIVATE_KEY
    claims = settings.VAPID_CLAIMS

    if not raw_key:
        logger.warning(
            "VAPID_PRIVATE_KEY is not set. "
            "Run: python manage.py generate_vapid_keys"
        )
        return None, None

    if not claims or not claims.get("sub"):
        logger.warning(
            'VAPID_CLAIMS is not set or missing "sub". '
            'Add: VAPID_CLAIMS = {"sub": "mailto:admin@socyfie.com"}'
        )
        return None, None

    # ── Format 1: PEM string (contains "BEGIN") ───────────────────────────────
    if "BEGIN" in raw_key:
        # Re-assemble in case the user's settings.py has literal \n strings
        # instead of real newlines (e.g. loaded from a .env file).
        if "\\n" in raw_key:
            raw_key = raw_key.replace("\\n", "\n")

        # Verify pywebpush can load it before returning
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            load_pem_private_key(raw_key.encode(), password=None)
        except Exception as exc:
            logger.error(
                "VAPID_PRIVATE_KEY looks like a PEM but failed to parse: %s\n"
                "This usually means newlines were lost when storing the key.\n"
                "Fix: run 'python manage.py generate_vapid_keys' to get a new\n"
                "single-line base64url key that has no newline dependency.",
                exc,
            )
            return None, None

        return raw_key, claims

    # ── Format 2: base64url scalar (output of updated generate_vapid_keys) ────
    try:
        pem = _base64url_to_pem(raw_key)
        logger.debug("VAPID private key decoded from base64url OK")
        return pem, claims
    except Exception as exc:
        logger.error(
            "Failed to decode VAPID_PRIVATE_KEY as base64url: %s\n"
            "Expected a 43-char base64url string from 'generate_vapid_keys'.\n"
            "Run: python manage.py generate_vapid_keys",
            exc,
        )
        return None, None

'''
# ─────────────────────────────────────────────────────────────────────────────
# Send Web Push
# ─────────────────────────────────────────────────────────────────────────────

def send_web_push_to_user(user_id: int, notification_data: dict) -> bool:
    """
    Send Web Push to every registered device for user_id.
    Called exclusively from the Celery task send_web_push_task.
    """
    notif_type = notification_data.get("type", "")
    if notif_type not in PUSH_WORTHY:
        return False

    subscriptions = get_push_subscriptions(user_id)
    if not subscriptions:
        logger.debug("No push subscriptions for user %s", user_id)
        return False

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning(
            "pywebpush not installed. Run: pip install pywebpush  "
            "then restart Celery workers."
        )
        return False

    private_key, claims = _get_vapid_config()
    if not private_key:
        return False

    payload = _build_push_payload(notification_data)
    stale   = []
    success = 0

    for sub in subscriptions:
        endpoint = sub.get("endpoint", "unknown")
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps(payload),
                #vapid_private_key=private_key,
                #vapid_claims=claims,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=settings.VAPID_CLAIMS,
            )
            success += 1
            logger.info("📲 Push sent → user %s (%s…)", user_id, endpoint[:55])

        except WebPushException as exc:
            status = exc.response.status_code if exc.response else None
            if status in (404, 410):
                stale.append(endpoint)
                logger.info("Removed stale push sub for user %s (HTTP %s)", user_id, status)
            elif status == 401:
                logger.error(
                    "Push auth 401 for user %s — VAPID keys mismatch. "
                    "Regen: python manage.py generate_vapid_keys",
                    user_id,
                )
            else:
                logger.warning("WebPushException for user %s (HTTP %s): %s",
                               user_id, status, exc)

        except Exception as exc:
            logger.error("Push send error for user %s: %s", user_id, exc)

    for ep in stale:
        delete_push_subscription(user_id, ep)

    return success > 0
'''

# ─────────────────────────────────────────────────────────────────────────────
# Payload builder (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _build_push_payload(notification_data: dict) -> dict:
    notif_type = notification_data.get("type", "")

    # Base URL of your deployed application
    base_url = "https://socyfie.com" 

    icon  = f"{base_url}/staticfiles/images/launchericon-192x192.png"
    badge = f"{base_url}/staticfiles/images/launchericon-192x192.png" 

    if notif_type == "new_message":
        sender  = notification_data.get("sender", "Someone")
        preview = (notification_data.get("message") or "Sent you a message")[:120]

        relative_url     = (notification_data.get("url")
                   or f"/user_messages_view/{sender}/")
        absolute_url = f"{base_url}{relative_url}" if relative_url.startswith("/") else relative_url

        
        return {
            "type"  : "new_message",
            "title" : f"💬 {sender}",
            "body"  : preview,
            "url"   : absolute_url,
            "tag"   : f"msg-{notification_data.get('message_id', '')}",
            "sender": sender,
            "icon"  : icon,
            "badge" : badge,
            "requireInteraction": False,
        }
        """

        # 🟢 FIX 2: Restructure payload to standard Web Push format
        return {
            "data": {
                "type"  : "new_message",
                "url"   : absolute_url,
                "sender": sender,
            },
            "notification": {
                "title" : f"💬 {sender}",
                "body"  : preview,
                "icon"  : icon,
                "badge" : badge,
                "tag"   : f"msg-{notification_data.get('message_id', '')}",
                "requireInteraction": False,
            }
        }
        """

    if notif_type == "group_message":
        sender = notification_data.get("sender", "Someone")
        group_name = notification_data.get("group_name", "Group")
        emoji = "📢" if notification_data.get("group_kind") == "broadcast" else "👥"
        fallback_url = reverse('only_message:group_list_view')

        return {
            "type": "group_message",
            "title": f"{emoji} {group_name}",
            "body": f"{sender}: {notification_data.get('message', '')}",
            "url": notification_data.get("url", fallback_url),
            "tag": notification_data.get("id", "group-msg"),
            "icon": icon, "badge": badge,
            "requireInteraction": False,
        }

    if notif_type == "incoming_call":
        caller     = notification_data.get("caller", "Someone")
        caller_pic = notification_data.get("caller_pic", "") or icon
        chat_url   = notification_data.get("chat_url", "/")
        call_type  = notification_data.get("call_type", "audio")
        emoji      = "📞" if call_type == "audio" else "🎥"
        return {
            "type"              : "incoming_call",
            "title"             : f"{emoji} Incoming {call_type} call",
            "body"              : f"{caller} is calling – tap to answer",
            "url"               : chat_url,
            "tag"               : "incoming-call",
            "renotify"          : True,                 # force sound/vibrate again on each repeat push
            "caller"            : caller,
            "caller_id"         : notification_data.get("caller_id"),
            "caller_pic"        : caller_pic,
            "call_type"         : call_type,
            "call_id"           : notification_data.get("call_id"),
            "icon"              : caller_pic,
            "badge"             : badge,
            "requireInteraction": True,
            "vibrate"           : [400, 200, 400, 200, 400, 800],   # phone-ring-ish cadence
            "actions"           : [
                {"action": "accept-call",  "title": "✅ Accept"},
                {"action": "decline-call", "title": "❌ Decline"},
            ],
        }

    if notif_type == "notion_notification":
        title = notification_data.get("title", "🔔 Socyfie")
        body  = notification_data.get("message") or "You have new activity"
        return {
            "type"              : "notion_notification",
            "title"             : title,
            "body"              : body,
            "url"               : notification_data.get("url", "/"),
            "tag"               : notification_data.get("id", "notion-notif"),
            "sender"            : notification_data.get("sender", "Socyfie"),
            "icon"              : icon,
            "badge"             : badge,
            "requireInteraction": False,
        }

    return {
        "type" : notif_type,
        "title": "Socyfie",
        "body" : notification_data.get("message", "You have a new notification"),
        "url"  : "/",
        "icon" : icon,
        "badge": badge,
        "requireInteraction": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Payload builder (unchanged)
# ─────────────────────────────────────────────────────────────────────────────




# ─────────────────────────────────────────────────────────────────────────────
# OneSignal — native push bridge for the Median-wrapped app
# ─────────────────────────────────────────────────────────────────────────────
 
ONESIGNAL_API_URL = "https://api.onesignal.com/notifications"
 
 
def _get_onesignal_config():
    """
    Return (app_id, rest_api_key) or (None, None).
 
    Both values live in your OneSignal dashboard under Settings → Keys & IDs,
    and must belong to the SAME OneSignal app configured in
    appconfigs.json → services.oneSignalV5.appId.
    """
    app_id  = getattr(settings, "ONESIGNAL_APP_ID", "")
    api_key = getattr(settings, "ONESIGNAL_REST_API_KEY", "")
 
    if not app_id or not api_key:
        logger.warning(
            "ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY not configured in "
            "settings.py — native push to the wrapped app is disabled."
        )
        return None, None
 
    return app_id, api_key
 
 
def _build_onesignal_payload(notification_data: dict) -> dict:
    """
    Reshapes the shared _build_push_payload() output into a OneSignal
    /notifications request body.
 
    `data.targetUrl` is what Median's native runtime reads to auto-launch the
    right in-app page when the notification is tapped — see
    appconfigs.json → services.oneSignalV5.notificationOpenedBehavior.
    No client-side JS is required for basic URL routing because of that.
    """
    base       = _build_push_payload(notification_data)
    notif_type = notification_data.get("type", "")
 
    body = {
        "headings": {"en": base.get("title", "Socyfie")},
        "contents": {"en": base.get("body", "You have a new notification")},
        "data": dict(base),  # full payload, also readable via
                              # median_onesignal_push_opened() client-side
    }
 
    if base.get("url"):
        body["data"]["targetUrl"] = base["url"]
 
    if base.get("icon"):
        body["large_icon"]       = base["icon"]
        body["chrome_web_icon"]  = base["icon"]
 
    if notif_type == "incoming_call":
        # Calls need to actually wake the device — high priority + sound,
        # not silently batched for later like a routine message push.
        body["priority"]      = 10
        body["ios_sound"]     = "default"
        body["android_sound"] = "default"
        body["android_group"] = "incoming_call"      # collapses repeats into one slot
        body["collapse_id"]   = f"call-{notification_data.get('call_id', '')}"  # re-alerts w/ same key on iOS
        body["android_visibility"] = 1                # show full content on lock screen

        pic = base.get("caller_pic") or notification_data.get("caller_pic")
        if pic:
            body["big_picture"]    = pic
            body["ios_attachments"] = {"call_avatar": pic}
        # Accept / Decline action buttons
        body["buttons"] = [
            {"id": "accept-call",  "text": "✅ Accept"},
            {"id": "decline-call", "text": "❌ Decline"},
        ]
        body["ios_category"] = "incoming_call"

    else:
        body["priority"] = 7
 
    return body
 
 
def send_onesignal_push_to_user(user_id: int, notification_data: dict) -> bool:
    """
    Send a push notification through OneSignal.
 
    This is the ONLY path that reaches the Median-wrapped native app while
    it's backgrounded or fully closed. Targets the user via OneSignal
    External ID, which must equal str(user_id) — the client must have
    already called:
 
        median.onesignal.login(String(currentUserId));
 
    at least once this session, or OneSignal has no device to target and
    this will return False with "0 recipients" logged.
    """
    notif_type = notification_data.get("type", "")
    if notif_type not in PUSH_WORTHY:
        return False
 
    app_id, api_key = _get_onesignal_config()
    if not app_id:
        return False
 
    try:
        import requests
    except ImportError:
        logger.warning(
            "requests is not installed. Run: pip install requests  "
            "then restart Celery workers."
        )
        return False
 
    payload = _build_onesignal_payload(notification_data)
    payload.update({
        "app_id": app_id,
        "target_channel": "push",
        "include_aliases": {"external_id": [str(user_id)]},
    })
 
    try:
        resp = requests.post(
            ONESIGNAL_API_URL,
            json=payload,
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=10,
        )
 
        resp_data = {}
        try:
            resp_data = resp.json()
        except ValueError:
            pass
 
        if resp.status_code in (200, 201):
            recipients = resp_data.get("recipients", 0)
            if recipients > 0:
                logger.info(
                    "📲 OneSignal push sent → user %s (%s recipient(s))",
                    user_id, recipients,
                )
                return True
 
            logger.info(
                "OneSignal accepted the request for user %s but found 0 "
                "recipients — confirm the client called "
                "median.onesignal.login('%s') this session.",
                user_id, user_id,
            )
            return False
 
        logger.warning(
            "OneSignal push failed for user %s (HTTP %s): %s",
            user_id, resp.status_code, resp_data or resp.text[:300],
        )
        return False
 
    except requests.exceptions.RequestException as exc:
        logger.error("OneSignal request error for user %s: %s", user_id, exc)
        return False
 
 
# ─────────────────────────────────────────────────────────────────────────────
# Send Web Push — dispatches BOTH delivery paths, independently
# ─────────────────────────────────────────────────────────────────────────────
import copy
def send_web_push_to_user(user_id: int, notification_data: dict) -> bool:
    """
    Send a notification to every device registered for user_id, across BOTH
    delivery paths:
 
      1. Browser Web Push (VAPID via pywebpush) — reaches real browsers and
         installed PWAs where notification permission was granted.
      2. OneSignal (native bridge) — reaches the Median-wrapped app even when
         it's backgrounded or fully closed.
 
    Called exclusively from the Celery task send_web_push_task — never from
    the main request/response cycle or a WebSocket consumer directly.
 
    IMPORTANT: this no longer returns early when there are no browser
    subscriptions, because wrapped-app users typically have none at all
    (their WebView never runs the browser's subscribe flow) — OneSignal must
    still get a chance to fire for them.
    """
    notif_type = notification_data.get("type", "")
    if notif_type not in PUSH_WORTHY:
        return False
 
    # ── 1. Browser Web Push (VAPID) ──────────────────────────────────────────
    browser_push_ok = False
    subscriptions   = get_push_subscriptions(user_id)
 
    if not subscriptions:
        logger.debug("No browser push subscriptions for user %s", user_id)
    else:
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            webpush = None
            logger.warning(
                "pywebpush not installed. Run: pip install pywebpush  "
                "then restart Celery workers."
            )
 
        if webpush:
            private_key, claims = _get_vapid_config()
            if private_key:
                payload = _build_push_payload(notification_data)
                stale   = []
                success = 0
 
                for sub in subscriptions:
                    endpoint = sub.get("endpoint", "unknown")
                    try:
                        webpush(
                            subscription_info=sub,
                            data=json.dumps(payload),
                            vapid_private_key=settings.VAPID_PRIVATE_KEY,
                            #vapid_claims=settings.VAPID_CLAIMS,
                            vapid_claims=copy.copy(settings.VAPID_CLAIMS),   # ← fresh dict per subscription
                        )
                        success += 1
                        logger.info("📲 Browser push sent → user %s (%s…)", user_id, endpoint[:55])
 
                    except WebPushException as exc:
                        status = exc.response.status_code if exc.response else None
                        if status in (404, 410):
                            stale.append(endpoint)
                            logger.info("Removed stale push sub for user %s (HTTP %s)", user_id, status)
                        elif status == 401:
                            logger.error(
                                "Push auth 401 for user %s — VAPID keys mismatch. "
                                "Regen: python manage.py generate_vapid_keys",
                                user_id,
                            )
                        else:
                            logger.warning("WebPushException for user %s (HTTP %s): %s",
                                           user_id, status, exc)
 
                    except Exception as exc:
                        logger.error("Push send error for user %s: %s", user_id, exc)
 
                for ep in stale:
                    delete_push_subscription(user_id, ep)
 
                browser_push_ok = success > 0
 
    # ── 2. OneSignal (native bridge) — independent of the path above ────────
    try:
        onesignal_ok = send_onesignal_push_to_user(user_id, notification_data)
    except Exception as exc:
        logger.warning("OneSignal dispatch failed (non-fatal) for user %s: %s", user_id, exc)
        onesignal_ok = False
 
    return browser_push_ok or onesignal_ok






