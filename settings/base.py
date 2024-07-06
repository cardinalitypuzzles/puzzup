"""
Django settings for PuzzUp project.

Generated by 'django-admin startproject' using Django 2.2.4.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import datetime
import json
import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("PUZZUP_SECRET", "secret-code-goes-here")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [""]

# Application definition

INSTALLED_APPS = [
    "puzzle_editing.apps.PuzzleEditingConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "import_export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "puzzle_editing.middleware.TimezoneMiddleware",
]

ROOT_URLCONF = "puzzup.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "puzzup.wsgi.application"


# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", "postgres://localhost:5432/puzzup")
    )
}

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "puzzle_editing.User"


# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"
USE_I18N = False
USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = os.path.normpath(os.path.join(BASE_DIR, "static"))
SITE_PASSWORD = os.environ.get("SITE_PASSWORD")


LOGIN_URL = "/accounts/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"


EMAIL_USE_TLS = True
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_PORT = os.getenv("EMAIL_PORT", 587)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_SUBJECT_PREFIX = "[Puzzup] "

DEFAULT_FROM_EMAIL = os.getenv("FROM_EMAIL", None)
AUTOPOSTPROD_EMAIL = os.getenv("FROM_EMAIL", None)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# 1 year, in seconds
SESSION_COOKIE_AGE = 365 * 24 * 60 * 60

# Ensure logs directory exists.
LOGS_DIR = BASE_DIR / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "django": {"format": "%(asctime)s [%(levelname)s] %(module)s\n%(message)s"},
        "puzzles": {"format": "%(asctime)s [%(levelname)s] %(message)s"},
    },
    "handlers": {
        "django": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "django.log"),
            "formatter": "django",
        },
        "puzzle": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "puzzle.log"),
            "formatter": "puzzles",
        },
        "request": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "request.log"),
            "formatter": "puzzles",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "puzzles",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["django"],
            "level": "DEBUG",
            "propagate": True,
        },
        "puzzle_editing": {
            "handlers": ["puzzle"],
            "level": "DEBUG",
        },
    },
}

# only if you want to do postprodding
HUNT_REPO_URL = os.environ.get("HUNT_REPO_URL", "")
HUNT_REPO = os.environ.get("HUNT_REPO", "")
HUNT_REPO_BRANCH = os.environ.get("HUNT_REPO_BRANCH", "main")
HUNT_REPO_CLIENT = os.path.join(HUNT_REPO, "client")
SSH_KEY = os.environ.get("SSH_KEY_PATH", "~/.ssh/id_rsa")

HUNT_TIME = datetime.datetime(
    year=2024,
    month=6,
    day=1,
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
    tzinfo=datetime.timezone.utc,
)

# API stuff
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

DRIVE_SETTINGS = {}
credentials_file = BASE_DIR / "credentials/drive-credentials.json"
if credentials_file.is_file():
    with open(credentials_file, "rt") as f:
        DRIVE_SETTINGS["credentials"] = json.load(f)

# Discord integration
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_APP_PUBLIC_KEY = os.environ.get("DISCORD_APP_PUBLIC_KEY")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_OAUTH_SCOPES = "identify"
DISCORD_TESTSOLVE_CHANNEL_ID = os.environ.get("DISCORD_TESTSOLVE_CHANNEL_ID")
TESTSOLVING_FOLDER_ID = os.environ.get("TESTSOLVING_FOLDER_ID")
TESTSOLVING_TEMPLATE_ID = os.environ.get("TESTSOLVING_TEMPLATE_ID", None)
PUZZLE_DRAFT_FOLDER_ID = os.environ.get("PUZZLE_DRAFT_FOLDER_ID")
FACTCHECKING_FOLDER_ID = os.environ.get("FACTCHECKING_FOLDER_ID")
FACTCHECKING_TEMPLATE_ID = os.environ.get("FACTCHECKING_TEMPLATE_ID")

POSTPROD_BRANCH_URL = os.environ.get("POSTPROD_BRANCH_URL", "")
POSTPROD_FACTORY_URL = os.environ.get("POSTPROD_FACTORY_URL", "")
POSTPROD_URL = os.environ.get("POSTPROD_URL", "")
PROD_URL = os.environ.get("PROD_URL", "")
PUZZUP_URL = os.environ.get("PUZZUP_URL", "")
