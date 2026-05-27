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


# =========================================================
# MAIN TASK
# =========================================================
@shared_task(
    bind=True,
    max_retries=3,
    soft_time_limit=300,
    time_limit=360
)
def process_message_file(
    self,
    message_id,
    sender_id,
    recipient_id
):
    """
    Process uploaded files asynchronously.

    Supports:
    - Images
    - Videos
    - Documents

    Compatible with:
    - S3
    - Cloudflare R2
    - DigitalOcean Spaces
    - Backblaze
    - Local storage
    """

    from .models import Message
    from .models import ConversationKey
    from .encryption_utils import decrypt_message

    try:

        logger.info(
            f"🔄 Starting file processing "
            f"for message {message_id}"
        )

        # =====================================================
        # GET MESSAGE
        # =====================================================
        try:
            message = Message.objects.get(id=message_id)

        except Message.DoesNotExist:

            logger.error(
                f"Message {message_id} not found"
            )

            return {
                'success': False,
                'error': 'Message not found'
            }

        # =====================================================
        # VALIDATE FILE
        # =====================================================
        if not message.file:

            logger.warning(
                f"No file attached to "
                f"message {message_id}"
            )

            return {
                'success': False,
                'error': 'No file attached'
            }

        # =====================================================
        # FILE INFO
        # =====================================================
        file_size = message.file.size
        file_name = os.path.basename(message.file.name)
        file_ext = os.path.splitext(file_name)[1].lower()

        logger.info(
            f"Processing file: "
            f"{file_name} ({file_size} bytes)"
        )

        # =====================================================
        # SEND INITIAL PROGRESS
        # =====================================================
        send_progress_update(
            message_id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 10,
                'message': 'Processing file...'
            }
        )

        # =====================================================
        # DETECT MIME TYPE
        # =====================================================
        mime_type = get_mime_type(file_name)

        # =====================================================
        # IMAGE
        # =====================================================
        if mime_type.startswith('image/'):

            result = process_image_file(
                message,
                file_name,
                sender_id,
                recipient_id
            )

        # =====================================================
        # VIDEO
        # =====================================================
        elif mime_type.startswith('video/'):

            result = process_video_file(
                message,
                file_name,
                file_ext,
                sender_id,
                recipient_id
            )

        # =====================================================
        # DOCUMENT
        # =====================================================
        elif mime_type in [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        ]:

            result = process_document_file(
                message,
                file_name,
                sender_id,
                recipient_id
            )

        # =====================================================
        # UNKNOWN FILE TYPE
        # =====================================================
        else:

            result = {
                'success': True,
                'processed': False
            }

            send_progress_update(
                message_id,
                sender_id,
                recipient_id,
                {
                    'status': 'processing',
                    'progress': 90,
                    'message': 'Finalizing...'
                }
            )

        # =====================================================
        # VALIDATE RESULT
        # =====================================================
        if not result['success']:

            raise Exception(
                result.get(
                    'error',
                    'Processing failed'
                )
            )

        # =====================================================
        # DECRYPT CONTENT
        # =====================================================
        decrypted_content = None

        if message.content:

            conversation = ConversationKey.objects.filter(
                participants=message.sender
            ).filter(
                participants=message.recipient
            ).first()

            if conversation:

                decrypted_content = decrypt_message(
                    message.content,
                    conversation.key.encode()
                )

        # =====================================================
        # SEND COMPLETION UPDATE
        # =====================================================
        send_progress_update(
            message_id,
            sender_id,
            recipient_id,
            {
                'status': 'completed',
                'progress': 100,
                'message': 'File ready',
                'file_url': message.file.url,
                'file_name': file_name
            }
        )

        # =====================================================
        # BROADCAST MESSAGE
        # =====================================================
        broadcast_message(
            message_id,
            sender_id,
            recipient_id,
            {
                #'type': 'message',
                'message_id': message.id,
                'content': decrypted_content,
                'sender': message.sender.username,
                'timestamp': message.timestamp.isoformat(),
                'file_url': message.file.url,
                'signature_valid': True
            }
        )

        # =====================================================
        # CLEAR CACHE FLAG
        # =====================================================
        cache.delete(f'file_processing:{message_id}')

        logger.info(
            f"✅ File processing completed "
            f"for message {message_id}"
        )

        return {
            'success': True,
            'message_id': message_id,
            'file_url': message.file.url
        }

    # =========================================================
    # TIMEOUT
    # =========================================================
    except SoftTimeLimitExceeded:

        logger.error(
            f"Task timeout for message {message_id}"
        )

        send_progress_update(
            message_id,
            sender_id,
            recipient_id,
            {
                'status': 'failed',
                'progress': 0,
                'message': 'Processing timeout'
            }
        )

        cache.delete(f'file_processing:{message_id}')

        return {
            'success': False,
            'error': 'Timeout'
        }

    # =========================================================
    # GENERAL ERRORS
    # =========================================================
    except Exception as e:

        logger.error(
            f"Error processing file "
            f"for message {message_id}: {e}",
            exc_info=True
        )

        send_progress_update(
            message_id,
            sender_id,
            recipient_id,
            {
                'status': 'failed',
                'progress': 0,
                'message': f'Processing failed: {str(e)}'
            }
        )

        cache.delete(f'file_processing:{message_id}')

        raise self.retry(
            exc=e,
            countdown=60 * (2 ** self.request.retries)
        )


# =========================================================
# IMAGE PROCESSING
# =========================================================
def process_image_file(
    message,
    file_name,
    sender_id,
    recipient_id
):

    try:

        logger.info(
            f"Processing image: {file_name}"
        )

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 30,
                'message': 'Optimizing image...'
            }
        )

        # OPEN FILE FROM STORAGE
        message.file.open('rb')

        with Image.open(message.file) as img:

            # =========================================
            # HANDLE EXIF ROTATION
            # =========================================
            try:

                exif = img._getexif()

                if exif:

                    orientation_key = next(
                        (
                            k for k, v
                            in ExifTags.TAGS.items()
                            if v == 'Orientation'
                        ),
                        None
                    )

                    if (
                        orientation_key and
                        orientation_key in exif
                    ):

                        orientation = exif[
                            orientation_key
                        ]

                        rotate_values = {
                            3: 180,
                            6: 270,
                            8: 90
                        }

                        if orientation in rotate_values:

                            img = img.rotate(
                                rotate_values[orientation],
                                expand=True
                            )

            except Exception as e:

                logger.warning(
                    f"EXIF rotation failed: {e}"
                )

            # =========================================
            # RGBA -> RGB
            # =========================================
            if img.mode in ('RGBA', 'LA', 'P'):

                background = Image.new(
                    'RGB',
                    img.size,
                    (255, 255, 255)
                )

                if img.mode == 'RGBA':

                    background.paste(
                        img,
                        mask=img.split()[-1]
                    )

                else:
                    background.paste(img)

                img = background

            # =========================================
            # UPDATE PROGRESS
            # =========================================
            send_progress_update(
                message.id,
                sender_id,
                recipient_id,
                {
                    'status': 'processing',
                    'progress': 60,
                    'message': 'Compressing...'
                }
            )

            # =========================================
            # RESIZE
            # =========================================
            max_width = 1920

            if img.width > max_width:

                ratio = max_width / img.width

                new_size = (
                    max_width,
                    int(img.height * ratio)
                )

                img = img.resize(
                    new_size,
                    Image.Resampling.LANCZOS
                )

            # =========================================
            # SAVE AS WEBP
            # =========================================
            output = BytesIO()

            img.save(
                output,
                format='WEBP',
                quality=85,
                method=6
            )

            output.seek(0)

            webp_filename = (
                os.path.splitext(file_name)[0]
                + '.webp'
            )

            # DELETE ORIGINAL
            try:
                message.file.delete(save=False)

            except Exception as e:

                logger.warning(
                    f"Delete original failed: {e}"
                )

            # SAVE NEW FILE
            message.file.save(
                webp_filename,
                ContentFile(output.read()),
                save=True
            )

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 90,
                'message': 'Finalizing...'
            }
        )

        return {
            'success': True,
            'processed': True
        }

    except Exception as e:

        logger.error(
            f"Image processing error: {e}",
            exc_info=True
        )

        return {
            'success': False,
            'error': str(e)
        }


# =========================================================
# VIDEO PROCESSING
# =========================================================
def process_video_file(
    message,
    file_name,
    file_ext,
    sender_id,
    recipient_id
):

    try:

        logger.info(
            f"Processing video: {file_name}"
        )

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 40,
                'message': 'Generating thumbnail...'
            }
        )

        # DOWNLOAD FILE TO TEMP
        message.file.open('rb')

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_ext
        ) as temp_video:

            temp_video.write(message.file.read())

            temp_video_path = temp_video.name

        thumb_filename = (
            f"thumb_"
            f"{os.path.splitext(file_name)[0]}.jpg"
        )

        thumb_output_path = os.path.join(
            tempfile.gettempdir(),
            thumb_filename
        )

        try:

            thumb_cmd = [
                "ffmpeg",
                "-ss", "1",
                "-i", temp_video_path,
                "-frames:v", "1",
                "-q:v", "4",
                "-update", "1",
                "-y",
                thumb_output_path
            ]

            subprocess.run(
                thumb_cmd,
                check=True,
                capture_output=True
            )

            logger.info(
                f"Thumbnail generated"
            )

        except subprocess.CalledProcessError as e:

            logger.warning(
                f"FFmpeg failed: {e}"
            )

        finally:

            # CLEANUP
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)

            if os.path.exists(thumb_output_path):
                os.remove(thumb_output_path)

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 90,
                'message': 'Finalizing...'
            }
        )

        return {
            'success': True,
            'processed': True
        }

    except Exception as e:

        logger.error(
            f"Video processing error: {e}",
            exc_info=True
        )

        return {
            'success': False,
            'error': str(e)
        }


# =========================================================
# DOCUMENT PROCESSING
# =========================================================
def process_document_file(
    message,
    file_name,
    sender_id,
    recipient_id
):

    try:

        logger.info(
            f"Processing document: {file_name}"
        )

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 50,
                'message': 'Validating document...'
            }
        )

        max_size = 10 * 1024 * 1024

        if message.file.size > max_size:

            return {
                'success': False,
                'error': 'File too large'
            }

        send_progress_update(
            message.id,
            sender_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 90,
                'message': 'Document ready...'
            }
        )

        return {
            'success': True,
            'processed': True
        }

    except Exception as e:

        logger.error(
            f"Document processing error: {e}",
            exc_info=True
        )

        return {
            'success': False,
            'error': str(e)
        }


# =========================================================
# SEND PROGRESS UPDATE
# =========================================================
def send_progress_update(
    message_id,
    sender_id,
    recipient_id,
    data
):

    try:

        channel_layer = get_channel_layer()

        sorted_ids = sorted([
            sender_id,
            recipient_id
        ])

        room_group_name = (
            f'chat_{sorted_ids[0]}_'
            f'{sorted_ids[1]}'
        )

        async_to_sync(
            channel_layer.group_send
        )(
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

        logger.error(
            f"Error sending progress update: {e}"
        )


# =========================================================
# BROADCAST MESSAGE
# =========================================================
def broadcast_message(
    message_id,
    sender_id,
    recipient_id,
    data
):

    try:

        channel_layer = get_channel_layer()

        sorted_ids = sorted([
            sender_id,
            recipient_id
        ])

        room_group_name = (
            f'chat_{sorted_ids[0]}_'
            f'{sorted_ids[1]}'
        )

        async_to_sync(
            channel_layer.group_send
        )(
            room_group_name,
            {
                'type': 'chat_message_broadcast',
                **data
            }
        )

        logger.info(
            f"Broadcast message {message_id}"
        )

    except Exception as e:

        logger.error(
            f"Broadcast failed: {e}"
        )


# =========================================================
# MIME TYPE
# =========================================================
def get_mime_type(filename):

    mime_type, _ = mimetypes.guess_type(filename)

    return mime_type or 'application/octet-stream'







# =========================================================
# FILE STATUS TASKS + WEBSOCKET HELPERS
# S3 / R2 / Spaces COMPATIBLE VERSION
# =========================================================

import os
import logging
import tempfile
import subprocess
import mimetypes

from io import BytesIO

from celery import shared_task

from django.core.files.base import ContentFile
from django.utils import timezone

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)


# =========================================================
# MAIN TASK
# =========================================================
@shared_task(bind=True, max_retries=3)
def process_uploaded_file(
    self,
    message_id,
    user_id,
    recipient_id
):
    """
    Process uploaded file in background

    - Compress images
    - Generate thumbnails
    - Validate files
    - Send WebSocket updates

    Fully compatible with:
    - S3
    - Cloudflare R2
    - DigitalOcean Spaces
    - Local storage
    """

    from .models import (
        Message,
        FileUploadStatus,
        ProcessedFile
    )

    try:

        # =====================================================
        # GET MESSAGE
        # =====================================================
        message = Message.objects.get(id=message_id)

        file_status, created = (
            FileUploadStatus.objects.get_or_create(
                message=message,
                defaults={
                    'status': 'processing',
                    'progress': 0
                }
            )
        )

        # =====================================================
        # INITIAL STATUS
        # =====================================================
        file_status.status = 'processing'
        file_status.progress = 10
        file_status.celery_task_id = self.request.id
        file_status.save()

        send_file_status_update(
            message_id,
            user_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 10,
                'message': 'Processing file...'
            }
        )

        logger.info(
            f"Processing file for message "
            f"{message_id}"
        )

        # =====================================================
        # VALIDATE FILE
        # =====================================================
        if not message.file:

            raise ValueError(
                "No file attached to message"
            )

        # =====================================================
        # FILE INFO
        # =====================================================
        file_size = message.file.size
        file_name = os.path.basename(
            message.file.name
        )

        file_ext = os.path.splitext(
            file_name
        )[1].lower()

        file_status.file_size = file_size
        file_status.file_type = file_ext
        file_status.progress = 20
        file_status.save()

        send_file_status_update(
            message_id,
            user_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 20,
                'message': 'Analyzing file...'
            }
        )

        # =====================================================
        # PROCESS BASED ON FILE TYPE
        # =====================================================
        if file_ext in [
            '.jpg',
            '.jpeg',
            '.png',
            '.gif',
            '.webp'
        ]:

            process_image(
                message,
                file_status,
                user_id,
                recipient_id
            )

        elif file_ext in [
            '.mp4',
            '.webm',
            '.ogg',
            '.mov'
        ]:

            process_video(
                message,
                file_status,
                user_id,
                recipient_id
            )

        elif file_ext in [
            '.pdf',
            '.doc',
            '.docx',
            '.xls',
            '.xlsx',
            '.ppt',
            '.pptx'
        ]:

            process_document(
                message,
                file_status,
                user_id,
                recipient_id
            )

        else:

            file_status.progress = 90
            file_status.save()

        # =====================================================
        # MARK COMPLETE
        # =====================================================
        file_status.status = 'completed'
        file_status.progress = 100
        file_status.completed_at = timezone.now()
        file_status.save()

        logger.info(
            f"✅ File processing completed "
            f"for message {message_id}"
        )

        # =====================================================
        # FINAL UPDATE
        # =====================================================
        send_file_status_update(
            message_id,
            user_id,
            recipient_id,
            {
                'status': 'completed',
                'progress': 100,
                'message': 'File ready',
                'file_url': message.file.url,
                'file_name': file_name,
                'file_size': file_size
            }
        )

        # =====================================================
        # BROADCAST MESSAGE
        # =====================================================
        broadcast_message_to_chat(
            message,
            user_id,
            recipient_id
        )

        return {
            'success': True,
            'message_id': message_id,
            'file_url': message.file.url
        }

    except Exception as e:

        logger.error(
            f"Error processing file "
            f"for message {message_id}: "
            f"{str(e)}",
            exc_info=True
        )

        try:

            file_status.status = 'failed'
            file_status.error_message = str(e)
            file_status.save()

            send_file_status_update(
                message_id,
                user_id,
                recipient_id,
                {
                    'status': 'failed',
                    'progress': 0,
                    'message': (
                        f'File processing failed: '
                        f'{str(e)}'
                    )
                }
            )

        except Exception:
            pass

        raise self.retry(
            exc=e,
            countdown=60
        )


# =========================================================
# IMAGE PROCESSING
# =========================================================
def process_image(
    message,
    file_status,
    user_id,
    recipient_id
):
    """
    Compress image + create thumbnail
    """

    from .models import ProcessedFile

    try:

        file_name = os.path.basename(
            message.file.name
        )

        # =====================================================
        # OPEN REMOTE FILE
        # =====================================================
        message.file.open('rb')

        with Image.open(message.file) as img:

            # =========================================
            # EXIF ROTATION
            # =========================================
            try:

                exif = img._getexif()

                if exif:

                    orientation_key = next(
                        (
                            k for k, v
                            in ExifTags.TAGS.items()
                            if v == 'Orientation'
                        ),
                        None
                    )

                    if (
                        orientation_key and
                        orientation_key in exif
                    ):

                        orientation = exif[
                            orientation_key
                        ]

                        rotate_values = {
                            3: 180,
                            6: 270,
                            8: 90
                        }

                        if orientation in rotate_values:

                            img = img.rotate(
                                rotate_values[
                                    orientation
                                ],
                                expand=True
                            )

            except Exception as e:

                logger.warning(
                    f"EXIF rotation failed: {e}"
                )

            # =========================================
            # RGBA -> RGB
            # =========================================
            if img.mode in (
                'RGBA',
                'LA',
                'P'
            ):

                background = Image.new(
                    'RGB',
                    img.size,
                    (255, 255, 255)
                )

                if img.mode == 'RGBA':

                    background.paste(
                        img,
                        mask=img.split()[-1]
                    )

                else:
                    background.paste(img)

                img = background

            # =========================================
            # UPDATE STATUS
            # =========================================
            file_status.progress = 40
            file_status.save()

            send_file_status_update(
                message.id,
                user_id,
                recipient_id,
                {
                    'status': 'processing',
                    'progress': 40,
                    'message': (
                        'Compressing image...'
                    )
                }
            )

            # =========================================
            # COMPRESS LARGE IMAGE
            # =========================================
            if message.file.size > (
                2 * 1024 * 1024
            ):

                output = BytesIO()

                img.save(
                    output,
                    format='WEBP',
                    quality=85,
                    method=6
                )

                output.seek(0)

                compressed_file = (
                    ProcessedFile.objects.create(
                        message=message,
                        file_type='compressed'
                    )
                )

                compressed_file.file.save(
                    (
                        f'compressed_'
                        f'{os.path.splitext(file_name)[0]}.webp'
                    ),
                    ContentFile(output.read()),
                    save=True
                )

                compressed_file.size = (
                    compressed_file.file.size
                )

                compressed_file.save()

                logger.info(
                    f"Compressed image "
                    f"saved"
                )

            # =========================================
            # THUMBNAIL
            # =========================================
            file_status.progress = 60
            file_status.save()

            send_file_status_update(
                message.id,
                user_id,
                recipient_id,
                {
                    'status': 'processing',
                    'progress': 60,
                    'message': (
                        'Creating thumbnail...'
                    )
                }
            )

            thumb_img = img.copy()

            thumb_img.thumbnail(
                (300, 300),
                Image.Resampling.LANCZOS
            )

            thumb_io = BytesIO()

            thumb_img.save(
                thumb_io,
                format='WEBP',
                quality=80
            )

            thumb_io.seek(0)

            thumbnail = (
                ProcessedFile.objects.create(
                    message=message,
                    file_type='thumbnail'
                )
            )

            thumbnail.file.save(
                (
                    f'thumb_'
                    f'{os.path.splitext(file_name)[0]}.webp'
                ),
                ContentFile(thumb_io.read()),
                save=True
            )

            thumbnail.size = (
                thumbnail.file.size
            )

            thumbnail.save()

            logger.info(
                f"Thumbnail created "
                f"for message {message.id}"
            )

            # =========================================
            # FINALIZING
            # =========================================
            file_status.progress = 80
            file_status.save()

            send_file_status_update(
                message.id,
                user_id,
                recipient_id,
                {
                    'status': 'processing',
                    'progress': 80,
                    'message': 'Finalizing...'
                }
            )

    except Exception as e:

        logger.error(
            f"Error processing image: "
            f"{str(e)}",
            exc_info=True
        )

        raise


# =========================================================
# VIDEO PROCESSING
# =========================================================
def process_video(
    message,
    file_status,
    user_id,
    recipient_id
):

    try:

        file_name = os.path.basename(
            message.file.name
        )

        file_ext = os.path.splitext(
            file_name
        )[1]

        file_status.progress = 50
        file_status.save()

        send_file_status_update(
            message.id,
            user_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 50,
                'message': 'Processing video...'
            }
        )

        # =====================================================
        # DOWNLOAD TEMP FILE
        # =====================================================
        message.file.open('rb')

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_ext
        ) as temp_video:

            temp_video.write(
                message.file.read()
            )

            temp_video_path = (
                temp_video.name
            )

        # =====================================================
        # GENERATE THUMBNAIL
        # =====================================================
        thumb_path = (
            f"{temp_video_path}.jpg"
        )

        try:

            subprocess.run(
                [
                    "ffmpeg",
                    "-ss",
                    "1",
                    "-i",
                    temp_video_path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "4",
                    "-y",
                    thumb_path
                ],
                check=True,
                capture_output=True
            )

            logger.info(
                f"Video thumbnail generated"
            )

        except subprocess.CalledProcessError as e:

            logger.warning(
                f"FFmpeg failed: {e}"
            )

        finally:

            # CLEANUP
            if os.path.exists(
                temp_video_path
            ):
                os.remove(
                    temp_video_path
                )

            if os.path.exists(
                thumb_path
            ):
                os.remove(
                    thumb_path
                )

        file_status.progress = 80
        file_status.save()

    except Exception as e:

        logger.error(
            f"Error processing video: "
            f"{str(e)}",
            exc_info=True
        )

        raise


# =========================================================
# DOCUMENT PROCESSING
# =========================================================
def process_document(
    message,
    file_status,
    user_id,
    recipient_id
):

    try:

        file_status.progress = 50
        file_status.save()

        send_file_status_update(
            message.id,
            user_id,
            recipient_id,
            {
                'status': 'processing',
                'progress': 50,
                'message': (
                    'Validating document...'
                )
            }
        )

        logger.info(
            f"Document processed "
            f"for message {message.id}"
        )

        file_status.progress = 80
        file_status.save()

    except Exception as e:

        logger.error(
            f"Error processing document: "
            f"{str(e)}",
            exc_info=True
        )

        raise


# =========================================================
# SEND FILE STATUS UPDATE
# =========================================================
def send_file_status_update(
    message_id,
    user_id,
    recipient_id,
    status_data
):

    try:

        channel_layer = get_channel_layer()

        sorted_ids = sorted([
            user_id,
            recipient_id
        ])

        room_group_name = (
            f'chat_{sorted_ids[0]}_'
            f'{sorted_ids[1]}'
        )

        async_to_sync(
            channel_layer.group_send
        )(
            room_group_name,
            {
                'type': 'file_status_update',
                'message_id': message_id,
                'status': status_data.get(
                    'status'
                ),
                'progress': status_data.get(
                    'progress'
                ),
                'message': status_data.get(
                    'message'
                ),
                'file_url': status_data.get(
                    'file_url'
                ),
                'file_name': status_data.get(
                    'file_name'
                ),
                'file_size': status_data.get(
                    'file_size'
                ),
            }
        )

        logger.info(
            f"Sent file status update "
            f"for message {message_id}"
        )

    except Exception as e:

        logger.error(
            f"Error sending "
            f"file status update: "
            f"{str(e)}",
            exc_info=True
        )


# =========================================================
# BROADCAST MESSAGE TO CHAT
# =========================================================
def broadcast_message_to_chat(
    message,
    user_id,
    recipient_id
):

    try:

        from .encryption_utils import (
            decrypt_message
        )

        from .models import (
            ConversationKey
        )

        # =====================================================
        # GET CONVERSATION KEY
        # =====================================================
        conversation = (
            ConversationKey.objects.filter(
                participants=message.sender
            ).filter(
                participants=message.recipient
            ).first()
        )

        if not conversation:

            logger.warning(
                f"No conversation key "
                f"found for message "
                f"{message.id}"
            )

            return

        # =====================================================
        # DECRYPT CONTENT
        # =====================================================
        decrypted_content = None

        if message.content:

            decrypted_content = decrypt_message(
                message.content,
                conversation.key.encode()
            )

        # =====================================================
        # SEND TO GROUP
        # =====================================================
        channel_layer = get_channel_layer()

        sorted_ids = sorted([
            user_id,
            recipient_id
        ])

        room_group_name = (
            f'chat_{sorted_ids[0]}_'
            f'{sorted_ids[1]}'
        )

        async_to_sync(
            channel_layer.group_send
        )(
            room_group_name,
            {
                'type': 'chat_message_broadcast',
                'message_id': message.id,
                'content': decrypted_content,
                'sender': message.sender.username,
                'sender_id': message.sender.id,
                'timestamp': (
                    message.timestamp.isoformat()
                ),
                'signature_valid': True,
                'file_url': (
                    message.file.url
                    if message.file
                    else None
                )
            }
        )

        logger.info(
            f"Broadcast message "
            f"{message.id} to chat"
        )

    except Exception as e:

        logger.error(
            f"Error broadcasting message: "
            f"{str(e)}",
            exc_info=True
        )
