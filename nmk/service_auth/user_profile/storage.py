
import os
import tempfile
import logging
import subprocess
from PIL import Image
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.conf import settings

logger = logging.getLogger(__name__)

class CompressedMediaStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        self.image_quality = kwargs.pop('image_quality', 85)
       # self.video_crf = kwargs.pop('video_crf', 28)
        self.max_image_dimension = kwargs.pop('max_image_dimension', 1920)
        self.audio_bitrate = kwargs.pop('audio_bitrate', '128k')
        super().__init__(*args, **kwargs)
        logger.info(f"CompressedMediaStorage initialized with image_quality={self.image_quality}, "
                   # f"video_crf={self.video_crf}, max_image_dimension={self.max_image_dimension},"
                    f"audio_bitrate={self.audio_bitrate}")
        
        
    def ensure_file_on_disk(self, content):
        """
        Ensures the file exists on disk by writing InMemoryUploadedFile to a temporary file.
        Returns the content itself if it's already a TemporaryUploadedFile.
        """
        if isinstance(content, TemporaryUploadedFile):
            # File is already on disk, no action needed
            return content

        if isinstance(content, InMemoryUploadedFile):
            # Write the in-memory file to a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                content.temporary_file_path = tmp_file.name  # Dynamically add temporary_file_path
            content.seek(0)  # Rewind the original file for further use
            logger.info(f"File written to temporary location: {content.temporary_file_path}")
            return content

        raise ValueError("Unsupported file type: must be an UploadedFile instance.")


    def _save(self, name, content):
        ext = os.path.splitext(name)[1].lower()
        logger.info(f"Saving file: {name} with extension: {ext}")
        if isinstance(content, (InMemoryUploadedFile, TemporaryUploadedFile)):
            if ext in ['.jpg', '.jpeg', '.png']:
                content = self.compress_image(content, ext, name)
           # elif ext in ['.mp4', '.mov', '.avi', '.mkv']:
               # content = self.compress_video(content, ext, name)
            elif ext in ['.mp3', '.wav', '.ogg']:
                content = self.compress_audio(content, ext, name)
        return super()._save(name, content)


    def compress_image(self, content, ext, name):
        logger.info(f"Compressing image: {name}")
        # logger.info(f"Original image size: {os.path.getsize(content.temporary_file_path())} bytes")
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                with Image.open(content) as img:
                    img = self.resize_image(img)
                    img.save(tmp_file.name, optimize=True, quality=self.image_quality)
                tmp_file.seek(0)
                file_size = os.path.getsize(tmp_file.name)
                logger.info(f"Compressed image {name}, size: {file_size} bytes")
                return InMemoryUploadedFile(
                    open(tmp_file.name, 'rb'), None, name, f'image/{ext[1:]}', file_size, None
                )
        except Exception as e:
            logger.error(f"Error compressing image {name}: {e}")
            return content  # Return original content if compression fails

    # def compress_image(self, content, ext, name):
    #     logger.info(f"Compressing image: {name}")

    #     # Ensure the file is on disk and has a temporary_file_path
    #     content = self.ensure_file_on_disk(content)

    #     try:
    #         # Log the original file size using the temporary file path
    #         original_size = os.path.getsize(content.temporary_file_path)
    #         logger.info(f"Original image size: {original_size} bytes")
    #     except Exception as e:
    #         logger.warning(f"Unable to retrieve original image size: {e}")

    #     try:
    #         with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
    #             with Image.open(content.temporary_file_path) as img:
    #                 img = self.resize_image(img)
    #                 img.save(tmp_file.name, optimize=True, quality=self.image_quality)
    #             tmp_file.seek(0)
    #             compressed_size = os.path.getsize(tmp_file.name)
    #             logger.info(f"Compressed image {name}, size: {compressed_size} bytes")
    #             return InMemoryUploadedFile(
    #                 open(tmp_file.name, 'rb'), None, name, f'image/{ext[1:]}', compressed_size, None
    #             )
    #     except Exception as e:
    #         logger.error(f"Error compressing image {name}: {e}")
    #         return content  # Return original content if compression fails
        finally:
            if hasattr(content, 'temporary_file_path'):
                try:
                    os.remove(content.temporary_file_path)
                    logger.info(f"Temporary file {content.temporary_file_path} deleted.")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to delete temporary file: {cleanup_error}")


    def resize_image(self, img):
        if max(img.size) > self.max_image_dimension:
            img.thumbnail((self.max_image_dimension, self.max_image_dimension))
        return img

    '''
    def compress_video(self, content, ext, name):
        logger.info(f"Compressing video: {name} with ffmpeg")
        # logger.debug(f"Running ffmpeg command: {' '.join(self.get_ffmpeg_command(content, ext, name))}")
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                output_path = tmp_file.name + "_compressed" + ext
                command = self.get_ffmpeg_command(content, ext, name)
                subprocess.run(command, check=True, capture_output=True)
                logger.info(f"Compressed video {name}, size: {os.path.getsize(output_path)} bytes")
                return InMemoryUploadedFile(
                    open(output_path, 'rb'), None, name, f'video/{ext[1:]}',
                    os.path.getsize(output_path), None
                )
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error compressing video {name}: {e.stderr.decode()}")
            return content  # Return original content if compression fails
        except Exception as e:
            logger.error(f"Error compressing video {name}: {e}")
            return content  # Return original content if compression fails
        
        finally:
            # Clean up any temporary files created
            if isinstance(content, InMemoryUploadedFile):
                try:
                    os.remove(content.temporary_file_path)
                    logger.info(f"Temporary file {content.temporary_file_path} deleted after processing.")
                except Exception as cleanup_error:
                    logger.error(f"Failed to delete temporary file: {cleanup_error}")

   
    
    def get_ffmpeg_command(self, content, ext, name):
        # Handle both InMemoryUploadedFile and TemporaryUploadedFile
        if isinstance(content, TemporaryUploadedFile):
            input_path = content.temporary_file_path
        elif isinstance(content, InMemoryUploadedFile):
            # Write InMemoryUploadedFile to a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                input_path = tmp_file.name
            # Rewind the content to enable re-reading if needed later
            content.seek(0)
        else:
            raise ValueError("Unsupported file type for ffmpeg command.")

        # Return the ffmpeg command using the appropriate input path
        return [
            'ffmpeg', '-i', input_path,
            '-vcodec', 'libx264', '-crf', str(self.video_crf),
            '-acodec', 'aac', '-strict', 'experimental',
            f"{name}_compressed{ext}"
        ]
    

    def compress_video(self, content, ext, name):
        logger.info(f"Compressing video: {name} with ffmpeg")
        try:
            # Write the uploaded content to a temporary file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                input_path = tmp_file.name
                output_path = f"{tmp_file.name}_compressed{ext}"

            # Generate the ffmpeg command
            command = self.get_ffmpeg_command(input_path, output_path)
            logger.debug(f"Running ffmpeg command: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True)

            # Log the successful compression
            logger.info(f"Compressed video {name}, size: {os.path.getsize(output_path)} bytes")
        
            # Return the compressed file
            return InMemoryUploadedFile(
                open(output_path, 'rb'), None, name, f'video/{ext[1:]}',
                os.path.getsize(output_path), None
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error compressing video {name}: {e.stderr.decode()}")
            return content  # Return original content if compression fails

        except Exception as e:
            logger.error(f"Error compressing video {name}: {e}")
            return content  # Return original content if compression fails

        finally:
            # Cleanup temporary files (both input and output)
            try:
                os.remove(input_path)
                os.remove(output_path)
                logger.info("Temporary files successfully deleted after processing.")
            except Exception as cleanup_error:
                logger.error(f"Failed to delete temporary files: {cleanup_error}")

    def get_ffmpeg_command(self, input_path, output_path):
        """
        Generate ffmpeg command to compress video
        """
        return [
            'ffmpeg', '-i', input_path,
            '-vcodec', 'libx264', '-crf', str(self.video_crf),
            '-acodec', 'aac', '-strict', 'experimental',
            '-preset', 'fast',  # Fast preset for quicker compression
            '-movflags', '+faststart',  # Optimize MP4 for web playback
            output_path
        ]
   '''

    def compress_audio(self, content, ext, name):
        logger.info(f"Compressing audio: {name} with ffmpeg")
        logger.debug(f"Running ffmpeg command: {' '.join(self.get_ffmpeg_audio_command(content, ext, name))}")
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content.read())
                tmp_file.flush()
                output_path = tmp_file.name + "_compressed" + ext
                command = self.get_ffmpeg_audio_command(content, ext, name)
                subprocess.run(command, check=True, capture_output=True)
                logger.info(f"Compressed audio {name}, size: {os.path.getsize(output_path)} bytes")
                return InMemoryUploadedFile(
                    open(output_path, 'rb'), None, name, f'audio/{ext[1:]}',
                    os.path.getsize(output_path), None
                )
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error compressing audio {name}: {e.stderr.decode()}")
            return content  # Return original content if compression fails
        except Exception as e:
            logger.error(f"Error compressing audio {name}: {e}")
            return content  # Return original content if compression fails
        
    def get_ffmpeg_audio_command(self, content, ext, name):
        return [
            'ffmpeg', '-i', content.temporary_file_path,
            '-b:a', self.audio_bitrate,
            '-ar', '44.1k',
            '-ac', '2',
            f"{name}_compressed{ext}"
        ]
