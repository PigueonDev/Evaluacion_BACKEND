from django.apps import AppConfig


class InstitucionalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'institucional'

    def ready(self):
        from django.db.models.signals import post_migrate

        from laserena import seguridad  # noqa: F401  registra las señales de login

        from .cuentas import sincronizar_grupos

        post_migrate.connect(sincronizar_grupos, dispatch_uid="sgr-sincronizar-grupos")
