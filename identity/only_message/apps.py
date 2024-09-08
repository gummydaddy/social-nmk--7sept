from django.apps import AppConfig


class OnlyMessageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "only_message"

    def ready(self):
        import only_message.signals
