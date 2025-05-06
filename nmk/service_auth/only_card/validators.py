# service_auth/only_card/validators.py

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
"""
class CustomUserAttributeSimilarityValidator:
    def validate(self, password, user=None):
        if not user:
            return

        username = getattr(user, "username", "") or ""
        email = getattr(user, "email", "") or ""
        first_name = getattr(user, "first_name", "") or ""

        # Convert to lowercase for case-insensitive match
        lower_password = password.lower()

        for attr_val in [username, email, first_name]:
            if attr_val and attr_val.lower() in lower_password:
                raise ValidationError(
                    _("The password is too similar to your personal information (e.g. username, email, first name)."),
                    code="password_too_similar",
                )

    def get_help_text(self):
        return _("Your password can’t contain your username, first name, or email.")
"""

class CustomUserAttributeSimilarityValidator:
    def validate(self, password, user=None):
        # This validator is now relaxed and doesn't enforce any similarity restriction.
        return

    def get_help_text(self):
        return ""
