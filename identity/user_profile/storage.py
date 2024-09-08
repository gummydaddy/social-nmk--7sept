import os
import tempfile
import logging
import subprocess
from PIL import Image
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class CompressedMediaStorage(FileSystemStorage):
    def _save(self, name, content):
        ext = os.path.splitext(name)[1].lower()
        if isinstance(content, (InMemoryUploadedFile, TemporaryUploadedFile)):
            if ext in ['.jpg', '.jpeg', '.png']:
                content = self.compress_image(content, ext, name)
            elif ext in ['.mp4', '.mov', '.avi', '.mkv']:
                content = self.compress_video(content, ext, name)
        return super()._save(name, content)

    def compress_image(self, content, ext, name):
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                with Image.open(content) as img:
                    img.save(tmp_file.name, optimize=True, quality=85)
                tmp_file.seek(0)
                file_size = os.path.getsize(tmp_file.name)
                logger.info(f"Compressed image {name}, size: {file_size} bytes")
                return InMemoryUploadedFile(
                    open(tmp_file.name, 'rb'), None, name, 'image/jpeg', file_size, None
                )
        except Exception as e:
            logger.error(f"Error compressing image {name}: {e}")
            raise

    def compress_video(self, content, ext, name):
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                output_path = tmp_file.name + "_compressed" + ext
                command = [
                    'ffmpeg', '-i', tmp_file.name, '-vcodec', 'libx264', '-crf', '28', output_path
                ]
                subprocess.run(command, check=True)
                logger.info(f"Compressed video {name}")
                return InMemoryUploadedFile(
                    open(output_path, 'rb'), None, name, 'video/mp4', os.path.getsize(output_path), None
                )
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error compressing video {name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error compressing video {name}: {e}")
            raise
