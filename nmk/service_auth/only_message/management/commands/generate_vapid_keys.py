"""
nmk/service_auth/only_message/management/commands/generate_vapid_keys.py
REPLACE previous version.

Root cause of "header too long":
  Previous version encoded the raw 32-byte EC scalar as base64url.
  pywebpush 2.x, when given a non-PEM string, does:
      base64url_decode(key) → treats result as PEM bytes → load_pem_private_key()
  Decoding a 32-byte scalar gives garbage, not a PEM — hence "header too long".

This version encodes the ENTIRE PEM file content as base64url.
  base64url_decode(VAPID_PRIVATE_KEY) → valid PEM bytes → load_pem_private_key() ✓
"""

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate VAPID key pair for Web Push"

    def handle(self, *args, **options):
        # ── Generate EC P-256 key pair ────────────────────────────────────────
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key  = private_key.public_key()

        # ── Private key: base64url( PEM file bytes ) ──────────────────────────
        # pywebpush 2.x: when vapid_private_key is not a PEM string/path,
        # it does:  base64url_decode(key)  then passes result to load_pem_private_key()
        # So we must encode the PEM content itself as base64url.
        '''
        private_pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        '''

        private_number = private_key.private_numbers().private_value

        private_raw = private_number.to_bytes(32, "big")

        #private_b64url = base64.urlsafe_b64encode(private_pem_bytes).decode().rstrip("=")
        private_b64url = (base64.urlsafe_b64encode(private_raw).decode().rstrip("="))

        # ── Public key: base64url( uncompressed EC point ) ────────────────────
        # This is the applicationServerKey the browser needs — unchanged format.
        public_raw    = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_b64url = base64.urlsafe_b64encode(public_raw).decode().rstrip("=")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✅  VAPID keys generated"))
        self.stdout.write("=" * 70)
        self.stdout.write("\nCopy these three lines into settings.py:\n")
        self.stdout.write(self.style.WARNING(
            f'\nVAPID_PUBLIC_KEY  = "{public_b64url}"'
        ))
        self.stdout.write(self.style.WARNING(
            f'\nVAPID_PRIVATE_KEY = "{private_b64url}"'
        ))
        self.stdout.write(self.style.WARNING(
            '\nVAPID_CLAIMS      = {"sub": "mailto:support@socyfie.com"}'
        ))
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(
            "\n⚠️  Both values are single-line strings — no triple-quotes, no newlines."
            "\n    Regenerate and replace BOTH keys in settings.py every time."
            "\n    After updating settings, restart Celery workers.\n"
        )



'''

"""
nmk/service_auth/only_message/management/commands/generate_vapid_keys.py
REPLACE the previous version.

Key change: VAPID_PRIVATE_KEY is now output as a 43-character base64url string
(the raw EC private scalar), not a multiline PEM.

Why: PEM keys stored in settings.py frequently lose their internal newlines
through copy-paste, .env files, or editor auto-formatting. OpenSSL then raises
"header too long" because PEM base64 lines must be ≤ 64 chars each.
A base64url scalar has no line structure — it can't be corrupted by newlines.
"""

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate VAPID key pair for Web Push (base64url format, no PEM)"

    def handle(self, *args, **options):
        # ── Generate EC P-256 key pair ────────────────────────────────────────
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key  = private_key.public_key()

        # ── Private key: raw 32-byte scalar → base64url (single clean line) ──
        raw_private   = private_key.private_numbers().private_value.to_bytes(32, "big")
        private_b64url = base64.urlsafe_b64encode(raw_private).decode().rstrip("=")

        # ── Public key: uncompressed point → base64url (for browser) ─────────
        public_raw    = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_b64url = base64.urlsafe_b64encode(public_raw).decode().rstrip("=")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✅  VAPID keys generated (base64url format)"))
        self.stdout.write("=" * 70)
        self.stdout.write("\nCopy these three lines into your settings.py:\n")
        self.stdout.write(self.style.WARNING(
            f'\nVAPID_PUBLIC_KEY  = "{public_b64url}"'
        ))
        self.stdout.write(self.style.WARNING(
            f'\nVAPID_PRIVATE_KEY = "{private_b64url}"'
        ))
        self.stdout.write(self.style.WARNING(
            '\nVAPID_CLAIMS      = {"sub": "mailto:support@socyfie.com"}'
        ))
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(
            "\n⚠️  VAPID_PRIVATE_KEY is a secret — treat it like a password."
            "\n    Both values are single-line strings with no newlines."
            "\n    Replace any previously generated keys in settings.py.\n"
        )

'''





"""
nmk/service_auth/only_message/management/commands/generate_vapid_keys.py

Generates an EC P-256 VAPID key pair and prints the values to add to
settings.py.  Uses only `cryptography`, which is already installed in
this project (used by encryption_utils.py).

Usage:
    python manage.py generate_vapid_keys
"""
'''
import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate VAPID key pair for Web Push notifications"

    def handle(self, *args, **options):
        # ── Generate EC P-256 key pair ────────────────────────────────────
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key  = private_key.public_key()

        # ── Private key as PEM string (store in settings.VAPID_PRIVATE_KEY) ─
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8").strip()

        # ── Public key as base64url (browser applicationServerKey) ──────────
        # The browser expects the uncompressed EC point (65 bytes) encoded as
        # base64url without padding.
        public_raw = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_b64url = base64.urlsafe_b64encode(public_raw).decode("utf-8").rstrip("=")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✅  VAPID keys generated"))
        self.stdout.write("=" * 70)
        self.stdout.write("\nAdd these to your settings.py:\n")

        self.stdout.write(self.style.WARNING('\nVAPID_PUBLIC_KEY = "' + public_b64url + '"'))

        self.stdout.write(self.style.WARNING("\nVAPID_PRIVATE_KEY = \"\"\""))
        self.stdout.write(self.style.WARNING(private_pem))
        self.stdout.write(self.style.WARNING('"""'))

        self.stdout.write(self.style.WARNING(
            '\nVAPID_CLAIMS = {"sub": "mailto:admin@yourdomain.com"}'
        ))

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(
            "\n⚠️  Keep VAPID_PRIVATE_KEY secret – treat it like a password.\n"
        )
'''
