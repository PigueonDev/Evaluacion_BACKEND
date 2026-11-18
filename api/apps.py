from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "API REST del SGR"

    def ready(self):
        from . import esquema  # noqa: F401  registra el esquema BearerAuth en drf-spectacular
