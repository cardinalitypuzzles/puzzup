import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from settings.base import *  # pylint: disable=unused-wildcard-import,wildcard-import

DEBUG = False
SECURE_SSL_REDIRECT = True

ALLOWED_HOSTS = ["127.0.0.1", "puzzup.vehemence.org"]

sentry_sdk.init(
    dsn="",
    integrations=[DjangoIntegration()],
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0,
    # If you wish to associate users to errors (assuming you are using
    # django.contrib.auth) you may enable sending PII data.
    send_default_pii=True,
)
