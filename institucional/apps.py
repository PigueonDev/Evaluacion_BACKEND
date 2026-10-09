from django.apps import AppConfig


class InstitucionalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'institucional'

    def ready(self):
        from laserena import seguridad  # noqa: F401  registra las señales de login
