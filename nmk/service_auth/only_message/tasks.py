import os
import logging
import tempfile
import subprocess
import mimetypes

from io import BytesIO

from PIL import Image, ExifTags, UnidentifiedImageError

from django.core.files.base import ContentFile
from django.core.cache import cache

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

# =========================================================
# TUNABLES
# =========================================================
WEBP_QUALITY = 80                    # was 85
WEBP_METHOD = 4                      # was 6 — much faster encode, negligible size diff
MAX_IMAGE_WIDTH = 1920
SMALL_FILE_SKIP_BYTES = 500 * 1024   # 500KB — don't bother re-encoding tiny files

DOCUMENT_MIME_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}


# =========================================================
# IMAGE PRE-OPTIMIZATION (runs BEFORE the file ever reaches
# storage — called synchronously from views.py, NOT Celery).
# This is what eliminates the double R2 write for images.
#
# IMPORTANT: `uploaded_file` (the original Django UploadedFile)
# is read into memory ONCE up front and its pointer is reset to
# 0 in a `finally` block *before* any PIL decoding happens. This
# guarantees that no matter what goes wrong below — corrupt image,
# unsupported format (HEIC/SVG), PIL exception, etc. — the caller
# can always safely fall back to saving `uploaded_file` as-is.
# =========================================================
def optimize_image_for_upload(uploaded_file):
    """
    Optimize an in-memory uploaded image before it's ever written to R2.

    Returns (ContentFile, new_filename) if re-encoding happened, or
    (None, None) if the original should be stored as-is (already an
    appropriately small/sized WebP, or optimization wasn't possible —
    in either case `uploaded_file` is left safe and fully readable
    from position 0).
    """
    original_name = uploaded_file.name
    file_ext = os.path.splitext(original_name)[1].lower()

    try:
        uploaded_file.seek(0)
        raw_bytes = uploaded_file.read()
        file_size = len(raw_bytes)
    except Exception as e:
        logger.warning(f"Could not read uploaded file for optimization: {e}")
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return None, None
    finally:
        # Always leave the original upload stream reset and intact,
        # regardless of what happens in the PIL logic below.
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    # Fast-path skip without decoding: already .webp and already small
    if file_ext == '.webp' and file_size <= SMALL_FILE_SKIP_BYTES:
        return None, None

    try:
        with Image.open(BytesIO(raw_bytes)) as img:

            already_webp = (img.format == 'WEBP')

            # Skip recompression: already webp, already small, already small dims
            if (
                already_webp
                and file_size <= SMALL_FILE_SKIP_BYTES
                and img.width <= MAX_IMAGE_WIDTH
            ):
                return None, None

            # Force decode now (safe — we're working off the in-memory copy)
            img.load()

            # ---- EXIF rotation ----
            try:
                exif = img._getexif() if hasattr(img, '_getexif') else None
                if exif:
                    orientation_key = next(
                        (k for k, v in ExifTags.TAGS.items() if v == 'Orientation'),
                        None
                    )
                    if orientation_key and orientation_key in exif:
                        orientation = exif[orientation_key]
                        rotate_values = {3: 180, 6: 270, 8: 90}
                        if orientation in rotate_values:
                            img = img.rotate(rotate_values[orientation], expand=True)
            except Exception as e:
                logger.warning(f"EXIF rotation failed: {e}")

            # ---- RGBA -> RGB ----
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img.convert('RGBA') if img.mode == 'P' else img)
                img = background

            # ---- Resize ----
            if img.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / img.width
                new_size = (MAX_IMAGE_WIDTH, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            img.save(output, format='WEBP', quality=WEBP_QUALITY, method=WEBP_METHOD)
            output.seek(0)

            webp_filename = os.path.splitext(original_name)[0] + '.webp'
            return ContentFile(output.read()), webp_filename

    except UnidentifiedImageError:
        # Not something PIL can open (e.g. SVG, some HEIC variants) —
        # store the original untouched rather than failing the send.
        logger.info(f"Skipping optimization — unsupported image format: {original_name}")
        return None, None

    except Exception as e:
        # Never block sending a message because of an optimization failure.
        logger.warning(f"Image pre-optimization skipped due to error: {e}")
        return None, None


# =========================================================
# MAIN CELERY TASK — routed to the dedicated `messages` queue
# so feed/recommendation jobs never delay chat uploads.
#
# Images no longer reach this task at all (they're optimized
# and stored in a single write from views.py). This task now
# only handles:
#   - videos    (thumbnail generation, streamed from R2)
#   - documents (lightweight validation)
# =========================================================
@shared_task(
    bind=True,
    queue='messages',
    max_retries=3,
    soft_time_limit=300,
    time_limit=360
)
def process_message_file(self, message_id, sender_id, recipient_id):
    """
    Background processing for non-image message attachments.

    NOTE: no decrypt_message() call and no full chat re-broadcast here.
    Clients already have the plaintext content locally (it's relayed
    over WS at send time, before this task even starts) — this task
    only ever ships file *metadata* (file_url / file_name) once
    processing is done.
    """
    from .models import Message

    try:
        logger.info(f"🔄 Starting background file processing for message {message_id}")

        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            logger.error(f"Message {message_id} not found")
            return {'success': False, 'error': 'Message not found'}

        if not message.file:
            logger.warning(f"No file attached to message {message_id}")
            return {'success': False, 'error': 'No file attached'}

        file_name = os.path.basename(message.file.name)
        file_ext = os.path.splitext(file_name)[1].lower()
        mime_type = get_mime_type(file_name)

        logger.info(f"Processing file: {file_name}")

        # ---- SINGLE "processing" EVENT ----
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 50,
            'message': 'Processing file...'
        })

        if mime_type.startswith('video/'):
            result = process_video_file(message, file_name, file_ext, sender_id, recipient_id)
        elif mime_type in DOCUMENT_MIME_TYPES:
            result = process_document_file(message, file_name, sender_id, recipient_id)
        else:
            result = {'success': True, 'processed': False}

        if not result['success']:
            raise Exception(result.get('error', 'Processing failed'))

        # ---- SINGLE "completed" EVENT — metadata only ----
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'completed',
            'progress': 100,
            'message': 'File ready',
            'file_url': message.file.url,
            'file_name': file_name
        })

        cache.delete(f'file_processing:{message_id}')

        logger.info(f"✅ File processing completed for message {message_id}")

        return {
            'success': True,
            'message_id': message_id,
            'file_url': message.file.url
        }

    except SoftTimeLimitExceeded:
        logger.error(f"Task timeout for message {message_id}")
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'failed',
            'progress': 0,
            'message': 'Processing timeout'
        })
        cache.delete(f'file_processing:{message_id}')
        return {'success': False, 'error': 'Timeout'}

    except Exception as e:
        logger.error(f"Error processing file for message {message_id}: {e}", exc_info=True)
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'failed',
            'progress': 0,
            'message': f'Processing failed: {str(e)}'
        })
        cache.delete(f'file_processing:{message_id}')
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# =========================================================
# VIDEO PROCESSING — thumbnail only.
# Streams the first frame directly from the R2 URL via ffmpeg
# instead of downloading the whole video to the worker first.
# Falls back to a full download only if URL-streaming fails
# (e.g. storage backend doesn't support range requests).
# =========================================================
def process_video_file(message, file_name, file_ext, sender_id, recipient_id):
    thumb_filename = f"thumb_{os.path.splitext(file_name)[0]}.jpg"
    thumb_output_path = os.path.join(tempfile.gettempdir(), thumb_filename)

    try:
        logger.info(f"Processing video (thumbnail only): {file_name}")

        file_url = None
        try:
            file_url = message.file.url
        except Exception as e:
            logger.warning(f"Could not resolve file URL: {e}")

        streamed_ok = False

        if file_url:
            try:
                thumb_cmd = [
                    "ffmpeg",
                    "-ss", "1",
                    "-i", file_url,          # ffmpeg pulls only the bytes it needs via HTTP range requests
                    "-frames:v", "1",
                    "-q:v", "4",
                    "-update", "1",
                    "-y",
                    thumb_output_path
                ]
                subprocess.run(thumb_cmd, check=True, capture_output=True, timeout=30)
                streamed_ok = True
                logger.info("Thumbnail generated via streamed URL (no full download)")
            except Exception as e:
                logger.warning(f"Streamed thumbnail generation failed, falling back: {e}")

        if not streamed_ok:
            # Fallback: only touch disk if streaming truly isn't possible
            temp_video_path = None
            try:
                message.file.open('rb')
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_video:
                    temp_video.write(message.file.read())
                    temp_video_path = temp_video.name

                subprocess.run(
                    [
                        "ffmpeg", "-ss", "1", "-i", temp_video_path,
                        "-frames:v", "1", "-q:v", "4", "-update", "1",
                        "-y", thumb_output_path
                    ],
                    check=True, capture_output=True, timeout=60
                )
            except subprocess.CalledProcessError as e:
                logger.warning(f"FFmpeg fallback failed: {e}")
            finally:
                if temp_video_path and os.path.exists(temp_video_path):
                    os.remove(temp_video_path)

        return {'success': True, 'processed': True}

    except Exception as e:
        logger.error(f"Video processing error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}

    finally:
        if os.path.exists(thumb_output_path):
            os.remove(thumb_output_path)


# =========================================================
# DOCUMENT PROCESSING — lightweight validation only.
# message.file.size is a metadata HEAD call on most storage
# backends, not a full download.
# =========================================================
def process_document_file(message, file_name, sender_id, recipient_id):
    try:
        logger.info(f"Validating document: {file_name}")

        max_size = 10 * 1024 * 1024
        if message.file.size > max_size:
            return {'success': False, 'error': 'File too large'}

        return {'success': True, 'processed': True}

    except Exception as e:
        logger.error(f"Document processing error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


# =========================================================
# WEBSOCKET HELPERS
# =========================================================
def send_progress_update(message_id, sender_id, recipient_id, data):
    try:
        channel_layer = get_channel_layer()
        sorted_ids = sorted([sender_id, recipient_id])
        room_group_name = f'chat_{sorted_ids[0]}_{sorted_ids[1]}'

        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'file_status_update',
                'message_id': message_id,
                'status': data.get('status'),
                'progress': data.get('progress'),
                'message': data.get('message'),
                'file_url': data.get('file_url'),
                'file_name': data.get('file_name'),
            }
        )
    except Exception as e:
        logger.error(f"Error sending progress update: {e}")


def get_mime_type(filename):
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


# =========================================================
# LEGACY TASK NAME — kept as a thin delegating stub so any
# stale queued tasks / external references don't break.
# =========================================================
@shared_task(bind=True, queue='messages', max_retries=3)
def process_uploaded_file(self, message_id, user_id, recipient_id):
    return process_message_file(
        message_id=message_id,
        sender_id=user_id,
        recipient_id=recipient_id
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


# ── add near the other push-related tasks ──────────────────────────────────

RING_INTERVAL_SECONDS = 4      # how often to re-push while ringing
RING_MAX_ATTEMPTS = 14         # ~56s of ringing, just under call_store.RING_TTL

@shared_task(bind=True, ignore_result=True, max_retries=0)
def ring_call_push(self, call_id, recipient_id, notification_data, attempt=1):
    """
    Re-sends the incoming_call push every RING_INTERVAL_SECONDS while the
    call is still 'ringing' in Redis (call_store.get_pending_call).

    Stops automatically once:
      - the callee answers   (call_store.mark_call_answered -> key deleted)
      - either side ends/rejects (call_store.end_pending_call -> key deleted)
      - RING_TTL expires      (key auto-expires in Redis)
      - RING_MAX_ATTEMPTS reached
    """
    from .call_store import get_pending_call
    from .push_notifications import send_web_push_to_user

    call = get_pending_call(call_id)
    if not call:
        logger.info(f"🔕 ring_call_push: call {call_id} no longer pending — stopping ringer")
        return

    try:
        send_web_push_to_user(recipient_id, notification_data)
        logger.info(f"🔔 ring_call_push: attempt {attempt} for call {call_id}")
    except Exception as exc:
        logger.warning(f"ring_call_push send failed (attempt {attempt}): {exc}")

    if attempt < RING_MAX_ATTEMPTS:
        ring_call_push.apply_async(
            kwargs={
                'call_id': call_id,
                'recipient_id': recipient_id,
                'notification_data': notification_data,
                'attempt': attempt + 1,
            },
            countdown=RING_INTERVAL_SECONDS,
        )



#Live
'''
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
'''



from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from service_auth.only_message import live_store as store
from service_auth.only_message import group_store


@shared_task
def cleanup_stale_live_rooms():
    rooms = store.list_active_rooms(limit=500)
    removed = 0

    channel_layer = get_channel_layer()

    for room in rooms:
        room_id = room["room_id"]

        if not store.heartbeat_alive(room_id):
            linked_gid = room.get("linked_group_id")

            # Delete the stale live room
            store.delete_room(room_id)
            removed += 1

            logger.info(
                "Removed stale live room: %s (host: %s)",
                room_id,
                room.get("host_username"),
            )

            # Notify linked group, if any
            if linked_gid:
                try:
                    msg = group_store.push_message(
                        linked_gid,
                        sender_id=0,
                        sender_username='',
                        sender_pic='',
                        content='🔴 Live stream ended',
                        message_type='system',
                    )

                    # Send system message to the group
                    async_to_sync(
                        channel_layer.group_send
                    )(
                        f"group_{linked_gid}",
                        {
                            "type": "group_message_event",
                            "message": msg,
                        },
                    )

                    # Notify connected clients that the live stream ended
                    async_to_sync(
                        channel_layer.group_send
                    )(
                        f"group_{linked_gid}",
                        {
                            "type": "live_ended_event",
                        },
                    )

                    logger.info(
                        "Sent live-ended notifications to group %s "
                        "for stale live room %s",
                        linked_gid,
                        room_id,
                    )

                except Exception:
                    logger.exception(
                        "Could not notify group %s about ended "
                        "live room %s",
                        linked_gid,
                        room_id,
                    )

    logger.info(
        "Cleanup complete. Removed %s stale live room(s).",
        removed,
    )

    return f"Removed {removed} stale live room(s)."
