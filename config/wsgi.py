"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
app = application

# Auto-migrate database tables for serverless / Vercel environments
try:
    from django.db import connection
    tables = connection.introspection.table_names()
    if 'django_site' not in tables or 'reader_book' not in tables:
        from django.core.management import call_command
        call_command('migrate', interactive=False)
        
except Exception as e:
    print("Auto-migration initialization note:", e)
