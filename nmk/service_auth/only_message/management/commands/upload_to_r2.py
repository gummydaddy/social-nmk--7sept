import os
import boto3
from django.conf import settings
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Upload all local media files to Cloudflare R2 bucket"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what will be uploaded without actually uploading",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip files that already exist in the bucket",
        )

    def handle(self, *args, **options):
        local_media_root = settings.MEDIA_ROOT
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        dry_run = options["dry_run"]
        skip_existing = options["skip_existing"]

        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        )

        uploaded_count = 0
        skipped_count = 0
        total_count = 0

        for root, dirs, files in os.walk(local_media_root):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, local_media_root)
                s3_key = relative_path.replace("\\", "/")  # For Windows compatibility

                total_count += 1

                if skip_existing:
                    try:
                        s3.head_object(Bucket=bucket_name, Key=s3_key)
                        self.stdout.write(f" Skipped (exists): {s3_key}")
                        skipped_count += 1
                        continue
                    except s3.exceptions.ClientError:
                        pass  # File does not exist, proceed to upload

                if dry_run:
                    self.stdout.write(f" [Dry run] Would upload: {s3_key}")
                else:
                    s3.upload_file(local_path, bucket_name, s3_key)
                    self.stdout.write(f" Uploaded: {s3_key}")
                    uploaded_count += 1

        self.stdout.write("\n Done!")
        self.stdout.write(f"Total files: {total_count}")
        self.stdout.write(f"Uploaded: {uploaded_count}")
        self.stdout.write(f"Skipped: {skipped_count}")
