from django.apps import AppConfig


class OnlyMessageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "service_auth.only_message"

    def ready(self):
        import service_auth.only_message.signals
