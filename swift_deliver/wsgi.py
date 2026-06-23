"""
WSGI config for swift_deliver project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'swift_deliver.settings')

application = get_wsgi_application()