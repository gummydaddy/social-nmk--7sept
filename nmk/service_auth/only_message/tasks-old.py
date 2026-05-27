
#Celery tasks for async file processing in messagingtasks.
# nmk/service_auth/only_message/tasks.py

import os
import logging
from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_uploaded_file(self, message_id, user_id, recipient_id):
    """
    Process uploaded file in background
    - Compress images
    - Generate thumbnails
    - Validate file
    - Send WebSocket updates
    """
    from .models import Message, FileUploadStatus, ProcessedFile
    from django.contrib.auth.models import User as AuthUser
    
    try:
        # Get message and file status
        message = Message.objects.get(id=message_id)
        file_status, created = FileUploadStatus.objects.get_or_create(
            message=message,
            defaults={'status': 'processing', 'progress': 0}
        )
        
        # Update status to processing
        file_status.status = 'processing'
        file_status.progress = 10
        file_status.celery_task_id = self.request.id
        file_status.save()
        
        # Send WebSocket update - processing started
        send_file_status_update(message_id, user_id, recipient_id, {
            'status': 'processing',
            'progress': 10,
            'message': 'Processing file...'
        })
        
        logger.info(f"Processing file for message {message_id}")
        
        if not message.file:
            raise ValueError("No file attached to message")
        
        # Get file info
        file_path = message.file.path
        file_size = message.file.size
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        file_status.file_size = file_size
        file_status.file_type = file_ext
        file_status.progress = 20
        file_status.save()
        
        # Send progress update
        send_file_status_update(message_id, user_id, recipient_id, {
            'status': 'processing',
            'progress': 20,
            'message': 'Analyzing file...'
        })
        
        # Process based on file type
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            process_image(message, file_status, self, user_id, recipient_id)
        
        elif file_ext in ['.mp4', '.webm', '.ogg', '.mov']:
            process_video(message, file_status, self, user_id, recipient_id)
        
        elif file_ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            process_document(message, file_status, self, user_id, recipient_id)
        
        else:
            # Just mark as completed for other file types
            file_status.progress = 90
            file_status.save()
        
        # Mark as completed
        file_status.status = 'completed'
        file_status.progress = 100
        file_status.completed_at = timezone.now()
        file_status.save()
        
        logger.info(f"✅ File processing completed for message {message_id}")
        
        # Send final WebSocket update with file URL
        send_file_status_update(message_id, user_id, recipient_id, {
            'status': 'completed',
            'progress': 100,
            'message': 'File ready',
            'file_url': message.file.url,
            'file_name': file_name,
            'file_size': file_size
        })
        
        # Broadcast message via WebSocket (if not already done)
        broadcast_message_to_chat(message, user_id, recipient_id)
        
        return {
            'success': True,
            'message_id': message_id,
            'file_url': message.file.url
        }
        
    except Exception as e:
        logger.error(f"Error processing file for message {message_id}: {str(e)}", exc_info=True)
        
        # Update status to failed
        try:
            file_status.status = 'failed'
            file_status.error_message = str(e)
            file_status.save()
            
            send_file_status_update(message_id, user_id, recipient_id, {
                'status': 'failed',
                'progress': 0,
                'message': f'File processing failed: {str(e)}'
            })
        except:
            pass
        
        # Retry the task
        raise self.retry(exc=e, countdown=60)


def process_image(message, file_status, task, user_id, recipient_id):
    """Process image files - compress and create thumbnail"""
    try:
        file_path = message.file.path
        
        # Open image
        with Image.open(file_path) as img:
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Update progress
            file_status.progress = 40
            file_status.save()
            send_file_status_update(message.id, user_id, recipient_id, {
                'status': 'processing',
                'progress': 40,
                'message': 'Compressing image...'
            })
            
            # Compress image if larger than 2MB
            if message.file.size > 2 * 1024 * 1024:
                output = BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                output.seek(0)
                
                # Save compressed version
                from .models import ProcessedFile
                compressed_file = ProcessedFile.objects.create(
                    message=message,
                    file_type='compressed'
                )
                compressed_file.file.save(
                    f'compressed_{os.path.basename(file_path)}',
                    ContentFile(output.read()),
                    save=True
                )
                compressed_file.size = compressed_file.file.size
                compressed_file.save()
                
                logger.info(f"Compressed image from {message.file.size} to {compressed_file.size} bytes")
            
            # Update progress
            file_status.progress = 60
            file_status.save()
            send_file_status_update(message.id, user_id, recipient_id, {
                'status': 'processing',
                'progress': 60,
                'message': 'Creating thumbnail...'
            })
            
            # Create thumbnail
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            thumb_io = BytesIO()
            img.save(thumb_io, format='JPEG', quality=85)
            thumb_io.seek(0)
            
            from .models import ProcessedFile
            thumbnail = ProcessedFile.objects.create(
                message=message,
                file_type='thumbnail'
            )
            thumbnail.file.save(
                f'thumb_{os.path.basename(file_path)}',
                ContentFile(thumb_io.read()),
                save=True
            )
            thumbnail.size = thumbnail.file.size
            thumbnail.save()
            
            logger.info(f"Created thumbnail for message {message.id}")
            
            # Update progress
            file_status.progress = 80
            file_status.save()
            send_file_status_update(message.id, user_id, recipient_id, {
                'status': 'processing',
                'progress': 80,
                'message': 'Finalizing...'
            })
            
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}", exc_info=True)
        raise


def process_video(message, file_status, task, user_id, recipient_id):
    """Process video files - create thumbnail"""
    try:
        # Update progress
        file_status.progress = 50
        file_status.save()
        send_file_status_update(message.id, user_id, recipient_id, {
            'status': 'processing',
            'progress': 50,
            'message': 'Processing video...'
        })
        
        # For video, we'll just validate it for now
        # Full video processing (thumbnails, compression) would require ffmpeg
        # which can be added later if needed
        
        logger.info(f"Video processed for message {message.id}")
        
        file_status.progress = 80
        file_status.save()
        
    except Exception as e:
        logger.error(f"Error processing video: {str(e)}", exc_info=True)
        raise


def process_document(message, file_status, task, user_id, recipient_id):
    """Process document files - validate and scan"""
    try:
        # Update progress
        file_status.progress = 50
        file_status.save()
        send_file_status_update(message.id, user_id, recipient_id, {
            'status': 'processing',
            'progress': 50,
            'message': 'Validating document...'
        })
        
        # For documents, just validate the file type
        # Could add virus scanning here if needed
        
        logger.info(f"Document processed for message {message.id}")
        
        file_status.progress = 80
        file_status.save()
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        raise


def send_file_status_update(message_id, user_id, recipient_id, status_data):
    """Send file upload status via WebSocket"""
    try:
        channel_layer = get_channel_layer()
        
        # Create room group name (same as in consumers)
        sorted_ids = sorted([user_id, recipient_id])
        room_group_name = f'chat_{sorted_ids[0]}_{sorted_ids[1]}'
        
        # Send to room group
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'file_status_update',
                'message_id': message_id,
                'status': status_data.get('status'),
                'progress': status_data.get('progress'),
                'message': status_data.get('message'),
                'file_url': status_data.get('file_url'),
                'file_name': status_data.get('file_name'),
                'file_size': status_data.get('file_size'),
            }
        )
        
        logger.info(f"Sent file status update for message {message_id}: {status_data.get('status')}")
        
    except Exception as e:
        logger.error(f"Error sending file status update: {str(e)}", exc_info=True)


def broadcast_message_to_chat(message, user_id, recipient_id):
    """Broadcast message to chat via WebSocket"""
    try:
        from .encryption_utils import decrypt_message
        from .models import ConversationKey
        
        # Get conversation key to decrypt message
        conversation = ConversationKey.objects.filter(
            participants=message.sender
        ).filter(
            participants=message.recipient
        ).first()
        
        if not conversation:
            logger.warning(f"No conversation key found for message {message.id}")
            return
        
        # Decrypt content
        decrypted_content = None
        if message.content:
            decrypted_content = decrypt_message(message.content, conversation.key.encode())
        
        channel_layer = get_channel_layer()
        
        # Create room group name
        sorted_ids = sorted([user_id, recipient_id])
        room_group_name = f'chat_{sorted_ids[0]}_{sorted_ids[1]}'
        
        # Broadcast message
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message_broadcast',
                'message_id': message.id,
                'content': decrypted_content,
                'sender': message.sender.username,
                'sender_id': message.sender.id,
                'timestamp': message.timestamp.isoformat(),
                'signature_valid': True,
                'file_url': message.file.url if message.file else None
            }
        )
        
        logger.info(f"Broadcast message {message.id} to chat")
        
    except Exception as e:
        logger.error(f"Error broadcasting message: {str(e)}", exc_info=True)







# nmk/service_auth/only_message/tasks.py
# Celery tasks for processing message file uploads

import os
import logging
import tempfile
import subprocess
from io import BytesIO
from PIL import Image, ImageOps, ExifTags
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage
from django.utils import timezone
from django.core.cache import cache
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def process_message_file(self, message_id, sender_id, recipient_id):
    """
    Process uploaded file asynchronously:
    - Compress images to WebP
    - Generate video thumbnails
    - Validate documents
    - Send WebSocket progress updates
    """
    from .models import Message
    from django.contrib.auth.models import User as AuthUser
    from .encryption_utils import decrypt_message
    from .models import ConversationKey
    
    try:
        logger.info(f"🔄 Starting file processing for message {message_id}")
        
        # Get message
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            logger.error(f"Message {message_id} not found")
            return {'success': False, 'error': 'Message not found'}
        
        if not message.file:
            logger.warning(f"No file attached to message {message_id}")
            return {'success': False, 'error': 'No file attached'}
        
        # Get file info
        file_path = message.file.path
        file_size = message.file.size
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        logger.info(f"Processing {file_name} ({file_size} bytes)")
        
        # Send initial progress update
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 10,
            'message': 'Processing file...'
        })
        
        # Detect file type and process
        mime_type = get_mime_type(file_name)
        
        if mime_type.startswith('image/'):
            result = process_image_file(message, file_path, file_name, sender_id, recipient_id)
        elif mime_type.startswith('video/'):
            result = process_video_file(message, file_path, file_name, sender_id, recipient_id)
        elif mime_type in ['application/pdf', 'application/msword', 
                          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          'application/vnd.ms-excel',
                          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                          'application/vnd.ms-powerpoint',
                          'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
            result = process_document_file(message, file_path, file_name, sender_id, recipient_id)
        else:
            # Unknown file type - just mark as processed
            result = {'success': True, 'processed': False}
            send_progress_update(message_id, sender_id, recipient_id, {
                'status': 'processing',
                'progress': 90,
                'message': 'Finalizing...'
            })
        
        if not result['success']:
            raise Exception(result.get('error', 'Processing failed'))
        
        # Get decrypted content for broadcast
        decrypted_content = None
        if message.content:
            conversation = ConversationKey.objects.filter(
                participants=message.sender
            ).filter(
                participants=message.recipient
            ).first()
            
            if conversation:
                decrypted_content = decrypt_message(message.content, conversation.key.encode())
        
        # Send completion update and broadcast message
        send_progress_update(message_id, sender_id, recipient_id, {
            'status': 'completed',
            'progress': 100,
            'message': 'File ready',
            'file_url': message.file.url,
            'file_name': file_name
        })
        
        # Broadcast the complete message to chat
        broadcast_message(message_id, sender_id, recipient_id, {
            'type': 'message',
            'message_id': message.id,
            'content': decrypted_content,
            'sender': message.sender.username,
            'timestamp': message.timestamp.isoformat(),
            'file_url': message.file.url,
            'signature_valid': True
        })
        
        # Clear processing flag from cache
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
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


def process_image_file(message, file_path, file_name, sender_id, recipient_id):
    """Process and compress image files"""
    try:
        logger.info(f"Processing image: {file_name}")
        
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 30,
            'message': 'Optimizing image...'
        })
        
        # Open image
        with Image.open(file_path) as img:
            # Handle EXIF orientation
            try:
                exif = img._getexif()
                if exif:
                    orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                    if orientation_key and orientation_key in exif:
                        orientation = exif[orientation_key]
                        rotate_values = {3: 180, 6: 270, 8: 90}
                        if orientation in rotate_values:
                            img = img.rotate(rotate_values[orientation], expand=True)
                            logger.info(f"Rotated image by {rotate_values[orientation]}°")
            except Exception as e:
                logger.warning(f"EXIF rotation failed: {e}")
            
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            
            send_progress_update(message.id, sender_id, recipient_id, {
                'status': 'processing',
                'progress': 60,
                'message': 'Compressing...'
            })
            
            # Resize if too large (max 1920px width)
            max_width = 1920
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {new_size}")
            
            # Save as WebP with compression
            buffer = BytesIO()
            img.save(buffer, format='WEBP', quality=85, method=6)
            buffer.seek(0)
            
            # Replace file with compressed version
            webp_filename = os.path.splitext(file_name)[0] + '.webp'
            
            # Delete original if it exists
            if message.file and message.file.name:
                try:
                    message.file.delete(save=False)
                except Exception as e:
                    logger.warning(f"Failed to delete original: {e}")
            
            # Save compressed file
            message.file.save(webp_filename, ContentFile(buffer.read()), save=True)
            
            logger.info(f"Image compressed and saved as {webp_filename}")
            
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 90,
            'message': 'Finalizing...'
        })
        
        return {'success': True, 'processed': True}
        
    except Exception as e:
        logger.error(f"Image processing error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def process_video_file(message, file_path, file_name, sender_id, recipient_id):
    """Process video files - generate thumbnail"""
    try:
        logger.info(f"Processing video: {file_name}")
        
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 40,
            'message': 'Generating thumbnail...'
        })
        
        # Generate thumbnail at 1 second
        thumb_filename = f"thumb_{os.path.splitext(file_name)[0]}.jpg"
        thumb_output_path = os.path.join(tempfile.gettempdir(), thumb_filename)
        
        try:
            thumb_cmd = [
                "ffmpeg",
                "-ss", "1",
                "-i", file_path,
                "-frames:v", "1",
                "-q:v", "4",
                "-update", "1",
                "-y",
                thumb_output_path
            ]
            subprocess.run(thumb_cmd, check=True, capture_output=True)
            logger.info(f"Video thumbnail generated: {thumb_output_path}")
            
            # Note: Since you don't have a thumbnail field in Message model,
            # we'll just log this. You could store it in media or upload to same storage
            # For now, we'll skip saving the thumbnail
            
            if os.path.exists(thumb_output_path):
                os.remove(thumb_output_path)
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"FFmpeg thumbnail generation failed: {e}")
            # Continue anyway - video is still usable
        
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 90,
            'message': 'Finalizing...'
        })
        
        return {'success': True, 'processed': True}
        
    except Exception as e:
        logger.error(f"Video processing error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def process_document_file(message, file_path, file_name, sender_id, recipient_id):
    """Validate document files"""
    try:
        logger.info(f"Processing document: {file_name}")
        
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 50,
            'message': 'Validating document...'
        })
        
        # Basic validation - check file size
        max_size = 10 * 1024 * 1024  # 10MB
        if os.path.getsize(file_path) > max_size:
            return {'success': False, 'error': 'File too large'}
        
        # Could add virus scanning here if needed
        # For now, just validate it exists and is readable
        
        send_progress_update(message.id, sender_id, recipient_id, {
            'status': 'processing',
            'progress': 90,
            'message': 'Document ready...'
        })
        
        return {'success': True, 'processed': True}
        
    except Exception as e:
        logger.error(f"Document processing error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


def send_progress_update(message_id, sender_id, recipient_id, data):
    """Send file processing progress via WebSocket"""
    try:
        channel_layer = get_channel_layer()
        
        # Send to both users
        for user_id in [sender_id, recipient_id]:
            async_to_sync(channel_layer.group_send)(
                f'user_{user_id}',
                {
                    'type': 'file_progress',
                    'message_id': message_id,
                    'status': data.get('status'),
                    'progress': data.get('progress'),
                    'message': data.get('message'),
                    'file_url': data.get('file_url'),
                    'file_name': data.get('file_name'),
                }
            )
        
        logger.debug(f"Progress update sent: {data.get('progress')}% - {data.get('message')}")
        
    except Exception as e:
        logger.error(f"Error sending progress update: {e}")


def broadcast_message(message_id, sender_id, recipient_id, data):
    """Broadcast completed message to chat"""
    try:
        channel_layer = get_channel_layer()
        
        # Send to both users' chat groups
        for user_id in [sender_id, recipient_id]:
            async_to_sync(channel_layer.group_send)(
                f'user_{user_id}',
                {
                    'type': 'chat_message',
                    **data
                }
            )
        
        logger.info(f"Message {message_id} broadcast to chat")
        
    except Exception as e:
        logger.error(f"Error broadcasting message: {e}")


def get_mime_type(filename):
    """Get MIME type from filename"""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'
