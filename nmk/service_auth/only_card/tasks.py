from celery import shared_task
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import UserUpload
from service_auth.only_card.utils import is_storage_full
from service_auth.user_profile.storage import CompressedMediaStorage
from PIL import Image, ExifTags, ImageFilter, ImageOps
from django.core.files.base import ContentFile
import os
import tempfile
import subprocess
import io


#@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True, queue='media_upload')
@shared_task
def process_file_upload(upload_id):
    try:
        upload = UserUpload.objects.get(id=upload_id)

        # Simulate storage check logic (adjust according to your business logic)
        user = upload.user
        if is_storage_full(user):  # You'll need to implement this
            upload.delete()  # Optionally roll back saved object
            # Log or notify user/admin
            return "Storage full"

        # If storage is fine, proceed (nothing to do since it's already saved)
        return "Upload successful"
    except UserUpload.DoesNotExist:
        return "Upload object not found"
    except Exception as e:
        return f"Error: {str(e)}"


"""
@shared_task(bind=True, max_retries=2, soft_time_limit=60, time_limit=75, acks_late=True)
def process_file_upload(self, upload_id, temp_file_path, file_name):
    try:
        upload = UserUpload.objects.get(id=upload_id)
        user = upload.user

        # Validate storage availability
        if is_storage_full(user):
            upload.delete()
            logger.warning(f"Upload deleted due to storage limits for user {user.username}")
            return "Storage full"

        # Save the file to the upload model
        with open(temp_file_path, 'rb') as f:
            upload.file.save(file_name, ContentFile(f.read()), save=False)

        upload.is_processed = True
        upload.save(update_fields=['file', 'is_processed'])

        logger.info(f"File '{file_name}' successfully attached to upload {upload_id}")
        return "Upload successful"

    except UserUpload.DoesNotExist:
        logger.error(f"Upload ID {upload_id} not found.")
        return "Upload object not found"

    except Exception as e:
        logger.error(f"Error processing upload {upload_id}: {e}")
        self.retry(exc=e)

    finally:
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"Temporary file deleted: {temp_file_path}")
        except Exception as e:
            logger.error(f"Failed to delete temporary file {temp_file_path}: {e}")



"""

"""
@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=70, acks_late=True)
def process_file_upload(self, upload_id):
    temp_in = None
    try:
        upload = UserUpload.objects.get(id=upload_id)

        # 1) Storage-space check
        if is_storage_full(upload.user):
            upload.delete()
            return "Storage full"

        storage = CompressedMediaStorage()
        orig_name = upload.file.name.lower()
        ext = os.path.splitext(orig_name)[1]

        # 2) Dump original to temp for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
            for chunk in upload.file.chunks():
                tf.write(chunk)
            temp_in = tf.name

        # 3a) IMAGE → convert to WEBP
        if ext in ('.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic'):
            img = Image.open(temp_in)

            # Auto‑rotate via EXIF
            try:
                exif = img._getexif()
                if exif:
                    orient = next((k for k,v in ExifTags.TAGS.items() if v=='Orientation'), None)
                    if orient and orient in exif:
                        deg = {3:180,6:270,8:90}.get(exif[orient])
                        if deg:
                            img = img.rotate(deg, expand=True)
            except Exception:
                pass

            # Optional further filters (if you want)
            # img = img.filter(ImageFilter.SHARPEN)

            # Resize + convert
            img = storage.resize_image(img)
            if img.mode == 'RGBA':
                img = img.convert('RGB')

            bio = io.BytesIO()
            webp_name = os.path.splitext(upload.file.name)[0] + '.webp'
            img.save(bio, format='WEBP', quality=storage.image_quality)
            upload.file.save(webp_name, ContentFile(bio.getvalue()), save=False)

        # 3b) VIDEO → transcode to WEBM via ffmpeg
        elif ext in ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm'):
            temp_out = temp_in + '.webm'
            cmd = [
                'ffmpeg', '-y', '-i', temp_in,
                '-c:v', 'libvpx-vp9', '-b:v', '1M',
                '-c:a', 'libvorbis',
                temp_out
            ]
            subprocess.run(cmd, check=True)

            with open(temp_out, 'rb') as f:
                out_name = os.path.splitext(upload.file.name)[0] + '.webm'
                upload.file.save(out_name, ContentFile(f.read()), save=False)
            os.remove(temp_out)

        # else: leave other types as-is (or you can delete/handle separately)

        upload.save(update_fields=['file'])
        return "Upload successful"

    except UserUpload.DoesNotExist:
        return "Upload object not found"

    except Exception as exc:
        # retry on error
        raise self.retry(exc=exc)

    finally:
        # clean up original temp
        if temp_in and os.path.exists(temp_in):
            try:
                os.remove(temp_in)
            except OSError:
                pass
"""
