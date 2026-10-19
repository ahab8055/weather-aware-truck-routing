"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Vercel uses an ephemeral /tmp SQLite file; create Django's built-in tables on cold start.
# Domain models are not persisted, so a per-instance migrate is enough.
if os.environ.get("VERCEL"):
    from django.core.management import call_command

    call_command("migrate", run_syncdb=True, verbosity=0)
