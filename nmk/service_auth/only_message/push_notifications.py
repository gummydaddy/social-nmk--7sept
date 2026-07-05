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

logger = logging.getLogger(__name__)

_PREFIX    = "push:subs:"
_TTL       = 60 * 60 * 24 * 90   # 90 days

PUSH_WORTHY = {"new_message", "incoming_call"}


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


# ─────────────────────────────────────────────────────────────────────────────
# Payload builder (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _build_push_payload(notification_data: dict) -> dict:
    notif_type = notification_data.get("type", "")
    icon  = "/static/images/android-icon-192x192.png"
    badge = "/static/images/android-icon-192x192.png"

    if notif_type == "new_message":
        sender  = notification_data.get("sender", "Someone")
        preview = (notification_data.get("message") or "Sent you a message")[:120]
        url     = (notification_data.get("url")
                   or f"/user_messages_view/{sender}/")
        return {
            "type"  : "new_message",
            "title" : f"💬 {sender}",
            "body"  : preview,
            "url"   : url,
            "tag"   : f"msg-{notification_data.get('message_id', '')}",
            "sender": sender,
            "icon"  : icon,
            "badge" : badge,
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
            "caller"            : caller,
            "caller_id"         : notification_data.get("caller_id"),
            "caller_pic"        : caller_pic,
            "call_type"         : call_type,
            "icon"              : caller_pic,
            "badge"             : badge,
            "requireInteraction": True,
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













"""
nmk/service_auth/only_message/push_notifications.py  — REPLACE previous version

Changes from previous version:
  • VAPID private key is .strip()ped before use — multiline strings in
    settings.py often have leading/trailing newlines that break PEM parsing.
  • Added _check_vapid_config() helper that logs a clear diagnosis on startup.
  • Stale subscription cleanup is more robust (handles bytes keys from Redis).
"""
'''
import json
import logging

from django.conf import settings
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

_PREFIX = "push:subs:"
_TTL    = 60 * 60 * 24 * 90   # 90 days

# Only these notification types trigger a push (not every WS signal)
PUSH_WORTHY = {"new_message", "incoming_call"}


# ─────────────────────────────────────────────────────────────────────────────
# Subscription CRUD
# ─────────────────────────────────────────────────────────────────────────────

def save_push_subscription(user_id: int, subscription_info: dict) -> bool:
    """Store a browser PushSubscription for user_id (keyed by endpoint)."""
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
    """Remove one device subscription."""
    try:
        r = get_redis_connection("default")
        r.hdel(f"{_PREFIX}{user_id}", endpoint)
        logger.info("Push subscription removed for user %s", user_id)
        return True
    except Exception as exc:
        logger.error("delete_push_subscription error: %s", exc)
        return False


def get_push_subscriptions(user_id: int) -> list:
    """Return all active PushSubscription dicts for user_id."""
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
    """Remove all subscriptions for a user (account deletion / opt-out)."""
    try:
        get_redis_connection("default").delete(f"{_PREFIX}{user_id}")
        return True
    except Exception as exc:
        logger.error("delete_all_push_subscriptions error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# VAPID config check
# ─────────────────────────────────────────────────────────────────────────────

def _get_vapid_config():
    """
    Return (private_key_str, claims) or (None, None) with a clear log message.

    Strips the private key to handle multiline strings in settings.py that
    start/end with newlines (a common copy-paste artefact).
    """
    private_key = getattr(settings, "VAPID_PRIVATE_KEY", "")
    claims      = getattr(settings, "VAPID_CLAIMS",      {})

    if not private_key:
        logger.warning(
            "VAPID_PRIVATE_KEY not set. "
            "Run: python manage.py generate_vapid_keys"
        )
        return None, None

    if not claims or not claims.get("sub"):
        logger.warning(
            'VAPID_CLAIMS not set or missing "sub" key. '
            'Add: VAPID_CLAIMS = {"sub": "mailto:admin@yourdomain.com"}'
        )
        return None, None

    # Strip leading/trailing whitespace and newlines
    private_key = private_key.strip()

    if "BEGIN" not in private_key:
        logger.error(
            "VAPID_PRIVATE_KEY does not look like a PEM string. "
            "It should start with -----BEGIN EC PRIVATE KEY----- "
            "or -----BEGIN PRIVATE KEY-----"
        )
        return None, None

    return private_key, claims


# ─────────────────────────────────────────────────────────────────────────────
# Send Web Push
# ─────────────────────────────────────────────────────────────────────────────

def send_web_push_to_user(user_id: int, notification_data: dict) -> bool:
    """
    Send Web Push to every registered device for user_id.

    Called from the Celery task send_web_push_task — never from the
    main request/response cycle or ASGI consumer directly.
    """
    notif_type = notification_data.get("type", "")
    if notif_type not in PUSH_WORTHY:
        return False

    subscriptions = get_push_subscriptions(user_id)
    if not subscriptions:
        logger.debug("No push subscriptions for user %s", user_id)
        return False

    # ── Guard: optional dependency ───────────────────────────────────────────
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning(
            "pywebpush is not installed. "
            "Run: pip install pywebpush   then restart Celery workers."
        )
        return False

    # ── Guard: VAPID config ──────────────────────────────────────────────────
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
                vapid_private_key=private_key,
                vapid_claims=claims,
            )
            success += 1
            logger.info("📲 Push sent → user %s (%s…)", user_id, endpoint[:55])

        except WebPushException as exc:
            status = exc.response.status_code if exc.response else None
            if status in (404, 410):
                # Subscription expired or revoked by browser
                stale.append(endpoint)
                logger.info(
                    "Removed stale push subscription for user %s (HTTP %s)",
                    user_id, status,
                )
            elif status == 401:
                logger.error(
                    "Push auth failed (HTTP 401) for user %s. "
                    "Check VAPID_PRIVATE_KEY and VAPID_CLAIMS.sub. "
                    "Also verify VAPID_PUBLIC_KEY matches the private key. "
                    "Regen keys: python manage.py generate_vapid_keys",
                    user_id,
                )
            else:
                logger.warning(
                    "WebPushException for user %s (HTTP %s): %s",
                    user_id, status, exc,
                )

        except Exception as exc:
            logger.error("Unexpected push error for user %s: %s", user_id, exc)

    for ep in stale:
        delete_push_subscription(user_id, ep)

    return success > 0


# ─────────────────────────────────────────────────────────────────────────────
# Push payload builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_push_payload(notification_data: dict) -> dict:
    """Convert internal notification dict → payload for the service worker."""
    notif_type = notification_data.get("type", "")
    icon  = "/static/images/android-icon-192x192.png"
    badge = "/static/images/android-icon-192x192.png"

    if notif_type == "new_message":
        sender  = notification_data.get("sender", "Someone")
        preview = (notification_data.get("message") or "Sent you a message")[:120]
        url     = (notification_data.get("url")
                   or f"/user_messages_view/{sender}/")
        return {
            "type"              : "new_message",
            "title"             : f"💬 {sender}",
            "body"              : preview,
            "url"               : url,
            "tag"               : f"msg-{notification_data.get('message_id', '')}",
            "sender"            : sender,
            "icon"              : icon,
            "badge"             : badge,
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
            "caller"            : caller,
            "caller_id"         : notification_data.get("caller_id"),
            "caller_pic"        : caller_pic,
            "call_type"         : call_type,
            "icon"              : caller_pic,
            "badge"             : badge,
            "requireInteraction": True,
        }

    # Fallback
    return {
        "type" : notif_type,
        "title": "Socyfie",
        "body" : notification_data.get("message", "You have a new notification"),
        "url"  : "/",
        "icon" : icon,
        "badge": badge,
        "requireInteraction": False,
    }
'''
