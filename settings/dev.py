# flake8: noqa
from decouple import config

from settings.base import *  # pylint: disable=unused-wildcard-import,wildcard-import

HUNT_REPO = config("HUNT_REPO", "")

DEBUG = True

EMAIL_SUBJECT_PREFIX = "[DEVELOPMENT] "

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INTERNAL_IPS = [
    "localhost",
    "127.0.0.1",
]
if not SITE_PASSWORD:
    SITE_PASSWORD = "racecar"

INSTALLED_APPS.append("debug_toolbar")
MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

# Allow for local (per-user) override
try:
    from settings_local import *  # pylint: disable=wildcard-import
except ImportError:
    pass
