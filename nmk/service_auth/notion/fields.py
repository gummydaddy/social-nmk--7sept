# fields.py

import binascii
import zlib
import base64
from django.db import models

class CompressedTextField(models.TextField):
    prefix = 'COMPRESSED:'  # Changed to string prefix

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        if isinstance(value, str) and value.startswith(self.prefix):
            # Extract Base64 encoded compressed data
            b64_data = value[len(self.prefix):]
            try:
                compressed_data = base64.b64decode(b64_data)
                decompressed = zlib.decompress(compressed_data).decode('utf-8')
                return decompressed
            except (zlib.error, binascii.Error):
                # Handle decompression or decoding errors gracefully
                return value  # Or return original value without prefix if corrupted
        return value

    def to_python(self, value):
        if value is None:
            return value
        # If already a string with prefix, process it
        if isinstance(value, str) and value.startswith(self.prefix):
            return self.from_db_value(value, None, None)
        return value

    def get_prep_value(self, value):
        if value is None:
            return value
        # Convert to bytes if it's a string
        if isinstance(value, str):
            value = value.encode('utf-8')
        # Compress and encode with Base64
        compressed = zlib.compress(value)
        b64_compressed = base64.b64encode(compressed).decode('ascii')
        return self.prefix + b64_compressed