from storages.backends.s3boto3 import S3Boto3Storage
import os
import tempfile
import logging
import subprocess
from PIL import Image
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.conf import settings
from io import BytesIO

logger = logging.getLogger(__name__)



class CompressedMediaStorage(S3Boto3Storage):
    file_overwrite = False

'''
class CompressedMediaStorage(S3Boto3Storage):
    def __init__(self, *args, **kwargs):
        self.image_quality = kwargs.pop('image_quality', 85)
        self.max_image_dimension = kwargs.pop('max_image_dimension', 1920)
        self.audio_bitrate = kwargs.pop('audio_bitrate', '128k')
        super().__init__(*args, **kwargs)
        logger.info(f"CompressedMediaStorage initialized for R2 bucket with "
                    f"image_quality={self.image_quality}, max_image_dimension={self.max_image_dimension}, "
                    f"audio_bitrate={self.audio_bitrate}")

    def _save(self, name, content):
        ext = os.path.splitext(name)[1].lower()
        logger.info(f"Saving file: {name} with extension: {ext}")

        try:
            if isinstance(content, (InMemoryUploadedFile, TemporaryUploadedFile)):
                if ext in ['.jpg', '.jpeg', '.png']:
                    content = self.compress_image(content, name)
        except Exception as e:
            logger.error(f"Compression failed for {name}: {e}")

        return super()._save(name, content)

    def compress_image(self, content, name):
        try:
            image = Image.open(content)
            image = self.resize_image(image)
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            webp_io = BytesIO()
            image.save(webp_io, format="WEBP", optimize=True, quality=self.image_quality)
            webp_io.seek(0)

            webp_file = InMemoryUploadedFile(
                webp_io, None, name, 'image/webp', webp_io.getbuffer().nbytes, None
            )
            return webp_file
        except Exception as e:
            logger.error(f"Error during image compression for {name}: {e}")
            return content  # Fallback

    def resize_image(self, image):
        if max(image.size) > self.max_image_dimension:
            image.thumbnail((self.max_image_dimension, self.max_image_dimension))
        return image

    def compress_audio(self, content, ext, name):
        logger.info(f"Audio compression placeholder for: {name} (not implemented)")
        return content  # Optional: implement audio compression later

'''




