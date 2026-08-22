
"""
nmk/service_auth/only_message/tasks.py

Fast, minimal file processing for direct messages.
Mirrors the speed settings from user_profile.tasks.process_media_upload:

  Images  → WebP 1280 px, quality 82, BICUBIC resize, method 4
  Videos  → H.264 libx264 veryfast crf 28, audio aac 96k, +faststart
  Docs    → 10 MB size guard only
"""

import os
import logging
import tempfile
import subprocess
import mimetypes

from io import BytesIO

from PIL import Image, ExifTags

from django.core.files.base import ContentFile
from django.core.cache import cache

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


# ── Tuning constants ────────────────────────────────────────────────────────────
# Keep these in sync with process_media_upload in user_profile/tasks.py

MAX_IMG_WIDTH = 1280          # was 1920 — smaller = faster encode & transfer
IMG_QUALITY   = 82            # was 85  — negligible visual difference in chat
WEBP_METHOD   = 4             # 0 fastest → 6 best; 4 is the sweet-spot for chat
MAX_DOC_BYTES = 10 * 1024 * 1024

DOCUMENT_TYPES = frozenset({
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
})


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN CELERY TASK
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def process_message_file(self, message_id, sender_id, recipient_id):
    """
    Process an uploaded message file asynchronously.
    Two WebSocket events only: one at start (20%), one on completion (100%).
    """
    from .models import Message, ConversationKey
    from .encryption_utils import decrypt_message

    try:
        logger.info(f"🔄 Starting file processing for message {message_id}")

        # ── fetch message ──────────────────────────────────────────────────────
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            logger.error(f"Message {message_id} not found")
            return {'success': False, 'error': 'Message not found'}

        if not message.file:
            logger.warning(f"No file on message {message_id}")
            return {'success': False, 'error': 'No file attached'}

        file_name = os.path.basename(message.file.name)
        mime_type = _mime(file_name)

        # Single "in-progress" WS update — no intermediate noise
        _ws(message_id, sender_id, recipient_id, 'processing', 20, 'Processing…')

        # ── dispatch ───────────────────────────────────────────────────────────
        if mime_type.startswith('image/'):
            ok, err = _process_image(message, file_name)

        elif mime_type.startswith('video/'):
            ok, err = _process_video(
                message, file_name,
                os.path.splitext(file_name)[1].lower(),
            )

        elif mime_type in DOCUMENT_TYPES:
            ok, err = _process_document(message)

        else:
            # Unknown type — leave the file as-is, still deliver it
            logger.info(f"Unknown MIME '{mime_type}' for message {message_id}, passing through")
            ok, err = True, None

        if not ok:
            raise Exception(err or 'Processing failed')

        # ── reload file URL (may have changed after save) ─────────────────────
        message.refresh_from_db()

        # ── decrypt content for WS broadcast ──────────────────────────────────
        decrypted_content = None
        if message.content:
            conv = (
                ConversationKey.objects
                .filter(participants=message.sender)
                .filter(participants=message.recipient)
                .first()
            )
            if conv:
                decrypted_content = decrypt_message(
                    message.content, conv.key.encode()
                )

        # ── completion events ──────────────────────────────────────────────────
        _ws(
            message_id, sender_id, recipient_id,
            'completed', 100, 'Ready',
            file_url=message.file.url,
            file_name=file_name,
        )

        _broadcast(message_id, sender_id, recipient_id, {
            'message_id':      message.id,
            'content':         decrypted_content,
            'sender':          message.sender.username,
            'sender_id':       message.sender.id,
            'timestamp':       message.timestamp.isoformat(),
            'file_url':        message.file.url,
            'signature_valid': True,
        })

        cache.delete(f'file_processing:{message_id}')
        logger.info(f"✅ Done message {message_id}")
        return {'success': True, 'message_id': message_id}

    except SoftTimeLimitExceeded:
        logger.error(f"Timeout on message {message_id}")
        _ws(message_id, sender_id, recipient_id, 'failed', 0, 'Processing timeout')
        cache.delete(f'file_processing:{message_id}')
        return {'success': False, 'error': 'Timeout'}

    except Exception as exc:
        logger.error(f"Error on message {message_id}: {exc}", exc_info=True)
        _ws(message_id, sender_id, recipient_id, 'failed', 0, str(exc)[:80])
        cache.delete(f'file_processing:{message_id}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE  — same pipeline as process_media_upload, tuned for speed
# ══════════════════════════════════════════════════════════════════════════════

def _process_image(message, file_name):
    """
    - Auto-rotate via EXIF
    - Flatten RGBA/P → RGB
    - Downscale to MAX_IMG_WIDTH (BICUBIC — faster than LANCZOS, fine for chat)
    - Encode to WebP quality=IMG_QUALITY, method=WEBP_METHOD
    - Replace original file in storage
    """
    try:
        message.file.open('rb')
        with Image.open(message.file) as img:

            # EXIF auto-rotation
            try:
                exif = img._getexif()
                if exif:
                    ori_key = next(
                        (k for k, v in ExifTags.TAGS.items() if v == 'Orientation'),
                        None,
                    )
                    if ori_key and ori_key in exif:
                        deg = {3: 180, 6: 270, 8: 90}.get(exif[ori_key])
                        if deg:
                            img = img.rotate(deg, expand=True)
                            logger.debug(f"EXIF rotate {deg}° for {file_name}")
            except Exception:
                pass  # non-JPEG or missing EXIF — safe to continue

            # Flatten to RGB
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ('RGB',):
                img = img.convert('RGB')

            # Resize — BICUBIC is noticeably faster than LANCZOS
            if img.width > MAX_IMG_WIDTH:
                new_h = int(img.height * (MAX_IMG_WIDTH / img.width))
                img = img.resize((MAX_IMG_WIDTH, new_h), Image.BICUBIC)

            buf = BytesIO()
            img.save(buf, format='WEBP', quality=IMG_QUALITY, method=WEBP_METHOD)
            buf.seek(0)

        webp_name = os.path.splitext(file_name)[0] + '.webp'

        # Delete original from storage before saving new version
        try:
            message.file.delete(save=False)
        except Exception:
            pass

        message.file.save(webp_name, ContentFile(buf.read()), save=True)
        logger.info(f"Image → {webp_name}")
        return True, None

    except Exception as exc:
        logger.error(f"Image processing failed: {exc}", exc_info=True)
        return False, str(exc)


# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO  — identical settings to process_media_upload (libx264 veryfast crf28)
#
#  BEFORE this change the task only generated a temp thumbnail and deleted it —
#  the raw video was served without ANY compression.  This fixes that.
# ══════════════════════════════════════════════════════════════════════════════

def _process_video(message, file_name, ext):
    """
    - Download original to a local temp file (required by FFmpeg)
    - Probe for audio stream
    - Compress: libx264 veryfast crf 28, scale to min(1280, iw), +faststart
    - Audio: aac 96 k 2-channel (if present), otherwise strip
    - Replace original file in storage with compressed MP4
    """
    tmp_in = tmp_out = None
    try:
        # Stream file from storage to local temp
        message.file.open('rb')
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as fh:
            fh.write(message.file.read())
            tmp_in = fh.name

        # Probe for audio
        has_audio = False
        try:
            probe = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-select_streams', 'a',
                    '-show_entries', 'stream=codec_type',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    tmp_in,
                ],
                capture_output=True, text=True,
            )
            has_audio = 'audio' in probe.stdout.lower()
        except Exception:
            pass

        mp4_name = os.path.splitext(file_name)[0] + '_c.mp4'
        tmp_out  = tmp_in + '_out.mp4'

        # Compress — mirrors process_media_upload exactly
        cmd = [
            'ffmpeg', '-i', tmp_in,
            '-vf',        "scale='min(1280,iw)':-2",
            '-c:v',       'libx264',
            '-preset',    'veryfast',
            '-crf',       '28',
            '-profile:v', 'main',
            '-pix_fmt',   'yuv420p',
            '-threads',   '0',
        ]
        cmd += (
            ['-c:a', 'aac', '-b:a', '96k', '-ac', '2']
            if has_audio else
            ['-an']
        )
        cmd += ['-movflags', '+faststart', '-y', tmp_out]

        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Video compressed → {mp4_name}")

        # Replace original in storage
        try:
            message.file.delete(save=False)
        except Exception:
            pass

        with open(tmp_out, 'rb') as fh:
            message.file.save(mp4_name, ContentFile(fh.read()), save=True)

        return True, None

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else ''
        logger.error(f"FFmpeg failed: {stderr}", exc_info=True)
        return False, 'Video compression failed'

    except Exception as exc:
        logger.error(f"Video processing failed: {exc}", exc_info=True)
        return False, str(exc)

    finally:
        for path in (tmp_in, tmp_out):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
#  DOCUMENT  — size guard only, no heavy processing
# ══════════════════════════════════════════════════════════════════════════════

def _process_document(message):
    try:
        if message.file.size > MAX_DOC_BYTES:
            return False, f'File exceeds {MAX_DOC_BYTES // (1024*1024)} MB limit'
        return True, None
    except Exception as exc:
        return False, str(exc)


# ══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _ws(message_id, sender_id, recipient_id, status, progress, msg,
        file_url=None, file_name=None):
    """Send a file_status_update event to the shared chat room."""
    try:
        layer = get_channel_layer()
        sids  = sorted([sender_id, recipient_id])
        group = f'chat_{sids[0]}_{sids[1]}'
        async_to_sync(layer.group_send)(group, {
            'type':       'file_status_update',
            'message_id': message_id,
            'status':     status,
            'progress':   progress,
            'message':    msg,
            'file_url':   file_url,
            'file_name':  file_name,
        })
    except Exception as exc:
        logger.error(f"WS update failed: {exc}")


def _broadcast(message_id, sender_id, recipient_id, data):
    """Broadcast chat_message_broadcast to both chat participants."""
    try:
        layer = get_channel_layer()
        sids  = sorted([sender_id, recipient_id])
        group = f'chat_{sids[0]}_{sids[1]}'
        async_to_sync(layer.group_send)(group, {
            'type': 'chat_message_broadcast',
            **data,
        })
        logger.info(f"Broadcast message {message_id}")
    except Exception as exc:
        logger.error(f"Broadcast failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  MIME HELPER  (kept as public name so views / tests can import it)
# ══════════════════════════════════════════════════════════════════════════════

def _mime(filename):
    mime, _ = mimetypes.guess_type(filename)
    return mime or 'application/octet-stream'


def get_mime_type(filename):
    """Public alias — existing imports remain valid."""
    return _mime(filename)


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY STUB
#  views.py imports process_uploaded_file at the top level.
#  Keep this to avoid ImportError — it delegates to process_message_file.
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3)
def process_uploaded_file(self, message_id, user_id, recipient_id):
    """
    Legacy task name — delegates to process_message_file.
    Kept so `from .tasks import process_uploaded_file` doesn't break.
    """
    return process_message_file.apply_async(
        kwargs={
            'message_id':   message_id,
            'sender_id':    user_id,
            'recipient_id': recipient_id,
        }
    )





@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    ignore_result=True,
    soft_time_limit=30,
    time_limit=40,
)
def send_web_push_task(self, user_id, notification_data):
    """
    Celery task: deliver a Web Push notification to every registered
    device for user_id.
 
    Runs in a Celery worker — completely off the Django/ASGI request path.
    Retries up to 2 times on transient errors (network, push service 5xx).
    Stale subscriptions (404/410) are removed automatically by
    send_web_push_to_user() and are not retried.
    """
    try:
        from .push_notifications import send_web_push_to_user
        send_web_push_to_user(user_id, notification_data)
    except Exception as exc:
        logger.warning(
            "send_web_push_task failed for user %s (attempt %s): %s",
            user_id, self.request.retries + 1, exc,
        )
        # Only retry on network-level errors, not on config errors
        error_str = str(exc).lower()
        if any(kw in error_str for kw in ("timeout", "connection", "network", "5")):
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                logger.info("Max push retries reached for user %s", user_id)

#Live
from service_auth.only_message import live_store as store

@shared_task
def cleanup_stale_live_rooms():
    rooms = store.list_active_rooms(limit=500)
    removed = 0

    for room in rooms:
        room_id = room["room_id"]

        if not store.heartbeat_alive(room_id):
            store.delete_room(room_id)
            removed += 1

    return f"Removed {removed} stale rooms."
