# fields.py

import zlib
from django.db import models

class CompressedTextField(models.TextField):
    prefix = b'COMPRESSED:'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        if isinstance(value, str):
            value = value.encode('latin1')
        if value.startswith(self.prefix):
            value = value[len(self.prefix):]
            try:
                return zlib.decompress(value).decode('utf-8')
            except zlib.error:
                pass  # handle decompression error gracefully
        return value.decode('utf-8')

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, bytes):
            if value.startswith(self.prefix):
                value = value[len(self.prefix):]
                try:
                    return zlib.decompress(value).decode('utf-8')
                except zlib.error:
                    pass  # handle decompression error gracefully
            return value.decode('utf-8')
        if isinstance(value, str):
            value = value.encode('latin1')
            if value.startswith(self.prefix):
                value = value[len(self.prefix):]
                try:
                    return zlib.decompress(value).decode('utf-8')
                except zlib.error:
                    pass  # handle decompression error gracefully
        return value

    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            value = value.encode('utf-8')
        return self.prefix + zlib.compress(value)
