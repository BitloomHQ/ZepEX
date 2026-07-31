"""
Django settings for backend project.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# --------------------------------------------------
# BASE DIR
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# LOAD ENV
# --------------------------------------------------

load_dotenv(BASE_DIR / ".env")


def _env_list(key: str, default: str = "") -> list[str]:
    value = os.getenv(key, default)
    return [item.strip() for item in value.split(",") if item.strip()]

# --------------------------------------------------
# SECURITY
# --------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "DJANGO_SECRET_KEY is not set. Copy backend/.env.example to backend/.env and set a secret key."
    )

DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------

INSTALLED_APPS = [
    # Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party Apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_celery_beat',
    'anymail',

    # Project Apps
    'platform_management',
    'tenants',
    'expenses',
    'authentication',
    'dashboards',
    'audit_logs',
    "drf_spectacular",
]

# --------------------------------------------------
# MIDDLEWARE
# --------------------------------------------------

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    'corsheaders.middleware.CorsMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# --------------------------------------------------
# ROOT URLS
# --------------------------------------------------

ROOT_URLCONF = 'backend.urls'

# --------------------------------------------------
# TEMPLATES
# --------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------
# WSGI
# --------------------------------------------------

WSGI_APPLICATION = 'backend.wsgi.application'

# --------------------------------------------------
# DATABASE
# --------------------------------------------------

import dj_database_url

DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL")
    )
}

# --------------------------------------------------
# PASSWORD VALIDATORS
# --------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# --------------------------------------------------
# INTERNATIONALIZATION
# --------------------------------------------------

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# --------------------------------------------------
# STATIC FILES
# --------------------------------------------------

STATIC_URL = 'static/'

# --------------------------------------------------
# MEDIA FILES
# --------------------------------------------------

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------
# DEFAULT PRIMARY KEY
# --------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------------------------------------
# DRF
# --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi.AutoSchema"
    ),
}

# --------------------------------------------------
# GEMINI
# --------------------------------------------------


# --------------------------------------------------
# CELERY
# --------------------------------------------------



# --------------------------------------------------
# CORS
# --------------------------------------------------

# --------------------------------------------------
# CORS
# --------------------------------------------------

_local_dev_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

CORS_ALLOWED_ORIGINS = _local_dev_origins + _env_list("DJANGO_CORS_ALLOWED_ORIGINS")

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = _local_dev_origins + _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# --------------------------------------------------
# EMAIL CONFIG
# --------------------------------------------------

EMAIL_HOST = os.getenv("EMAIL_HOST") or os.getenv("SMTP_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or os.getenv("SMTP_PORT") or 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER") or os.getenv("SMTP_USER")
_raw_email_password = os.getenv("EMAIL_HOST_PASSWORD") or os.getenv("SMTP_PASS") or ""
# Gmail app passwords are often pasted with spaces; SMTP expects the 16-char token.
EMAIL_HOST_PASSWORD = _raw_email_password.replace(" ", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("SMTP_FROM")

_email_use_tls = os.getenv("EMAIL_USE_TLS")
if _email_use_tls is None:
    smtp_secure = os.getenv("SMTP_SECURE", "false").strip().lower()
    EMAIL_USE_TLS = smtp_secure not in ("true", "1", "yes")
else:
    EMAIL_USE_TLS = _email_use_tls.strip().lower() in ("true", "1", "yes")

EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))

EMAIL_BACKEND = None
ANYMAIL = {}

match ENVIRONMENT:
    case "testing":
        # Render / staging — Resend (SMTP blocked on most PaaS hosts)
        EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
        ANYMAIL = {
            "RESEND_API_KEY": os.getenv("RESEND_API_KEY", ""),
        }
    case "development" | "local":
        # Local machine — Gmail SMTP
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    case "production":
        # Not configured yet — set EMAIL_BACKEND when ready
        pass
    case _:
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

if os.getenv("EMAIL_BACKEND"):
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
elif EMAIL_BACKEND is None:
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"




CELERY_TASK_ALWAYS_EAGER = os.getenv(
    "CELERY_TASK_ALWAYS_EAGER",
    "True" if DEBUG else "False",
) == "True"

CELERY_TASK_EAGER_PROPAGATES = True
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "scheduled-external-database-sync-every-night": {
        "task": "tenants.tasks.scheduled_external_database_sync",
        "schedule": crontab(hour=2, minute=0),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ZepEx API",
    "DESCRIPTION": (
        "Enterprise SaaS Expense Reimbursement "
        "Management System APIs"
    ),
    "VERSION": "1.0.0",

    "SERVE_INCLUDE_SCHEMA": False,

    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
    },
}

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "redis://localhost:6379/0"
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/0"
)

FRONTEND_LOGIN_URL = os.getenv(
    "FRONTEND_LOGIN_URL",
    "http://localhost:5173/login"
)


# --------------------------------------------------
# CURRENCY EXCHANGE
# --------------------------------------------------

EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")

EXCHANGE_RATE_PROVIDER = os.getenv(
    "EXCHANGE_RATE_PROVIDER",
    "ExchangeRate API"
)

EXCHANGE_RATE_API_URL = os.getenv(
    "EXCHANGE_RATE_API_URL",
    "https://v6.exchangerate-api.com/v6"
)

PLATFORM_RECEIPT_EMAIL = os.getenv(
    "PLATFORM_RECEIPT_EMAIL",
    "receipts@zepex.ai"
)

import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Receipt AI Model
GEMINI_RECEIPT_MODEL = os.getenv(
    "GEMINI_RECEIPT_MODEL",
    "gemini-2.5-flash"
)

# Policy AI Model
GEMINI_POLICY_MODEL = os.getenv(
    "GEMINI_POLICY_MODEL",
    "gemini-2.5-flash"
)

# API Base URL
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

VERIFY_COMPANY_EMAIL_DOMAIN = (
    os.getenv(
        "VERIFY_COMPANY_EMAIL_DOMAIN",
        "False",
    ).lower()
    == "true"
)

import os

IMAP_HOST = os.getenv("IMAP_HOST")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
IMAP_EMAIL = os.getenv("IMAP_EMAIL")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")


# --------------------------------------------------
# CELERY
# --------------------------------------------------

from celery.schedules import crontab

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = "Asia/Kolkata"

CELERY_ENABLE_UTC = True

CELERY_TASK_ALWAYS_EAGER = (
    os.getenv(
        "CELERY_TASK_ALWAYS_EAGER",
        "True" if DEBUG else "False",
    )
    == "True"
)

CELERY_TASK_EAGER_PROPAGATES = True

CELERY_BEAT_SCHEDULER = (
    "django_celery_beat.schedulers:DatabaseScheduler"
)

CELERY_BEAT_SCHEDULE = {
    "fetch-reimbursement-emails": {
        "task": "expenses.tasks.fetch_emails_task",
        "schedule": 60.0,
    },

    "scheduled-external-database-sync-every-night": {
        "task": "tenants.tasks.scheduled_external_database_sync",
        "schedule": crontab(hour=2, minute=0),
    },
}

