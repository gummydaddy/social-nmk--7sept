from django.apps import AppConfig


class UserProfileConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "user_profile"
    path = './user_profile'
    label = 'user_profile'

    def ready(self):
        import user_profile.signals  # Import the signals module