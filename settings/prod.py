import sentry_sdk
from django.core.exceptions import DisallowedHost
from sentry_sdk.integrations.django import DjangoIntegration

from settings.base import *  # noqa: F403
from settings.sentry import before_send_transaction

DEBUG = False
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_PORT = True

ALLOWED_HOSTS = [".herokuapp.com"]


sentry_sdk.init(
    dsn="https://d3e924ca08ac12b462b61e5e17c73523@o4506595254599680.ingest.sentry.io/4506595264954368",
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
    # If you wish to associate users to errors (assuming you are using
    # django.contrib.auth) you may enable sending PII data.
    send_default_pii=True,
    ignore_errors=[DisallowedHost],
    before_send_transaction=before_send_transaction,
)
