from django.apps import AppConfig


class UserProfileConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "service_auth.user_profile"
    path = './user_profile'
    #label = 'user_profile'
    #label = 'service_user_profile'   # must be unique across all INSTALLED_APPS


    def ready(self):
        import service_auth.user_profile.signals  # Import the signals module
