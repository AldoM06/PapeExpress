from django.apps import AppConfig


class PosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pos'
    verbose_name = 'Punto de Venta'

    def ready(self):
        # Registrar tareas programadas al iniciar
        try:
            from pos import tasks  # noqa
        except Exception:
            pass
