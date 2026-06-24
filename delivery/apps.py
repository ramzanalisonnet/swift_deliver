"""
App configuration with startup data seeding.
"""
from django.apps import AppConfig

class DeliveryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'delivery'

    def ready(self):
        # Import here to avoid AppRegistryNotReady
        from .utils import ensure_locations
        ensure_locations()