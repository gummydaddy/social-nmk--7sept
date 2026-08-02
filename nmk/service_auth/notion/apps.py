from django.apps import AppConfig


class NotionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "service_auth.notion"

    def ready(self):
        import service_auth.notion.signals
