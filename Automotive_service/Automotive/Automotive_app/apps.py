from django.apps import AppConfig

class AutomotiveAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Automotive_app' # Ensure this matches your folder name

    def ready(self):
        # This import is critical for signals to function
        import Automotive_app.signals