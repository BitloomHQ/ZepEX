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
    'expenses.apps.ExpensesConfig',
    'authentication',
    'dashboards',
    'audit_logs',
    "drf_spectacular",
    "platform_access",
    "integrations"
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

# Prefer S3_* (Supabase / S3-compatible). AWS_* kept as fallbacks.
AWS_STORAGE_BUCKET_NAME = (
    os.getenv("S3_BUCKET") or os.getenv("AWS_STORAGE_BUCKET_NAME") or ""
).strip()
AWS_ACCESS_KEY_ID = (
    os.getenv("S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID") or ""
).strip()
AWS_SECRET_ACCESS_KEY = (
    os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or ""
).strip()
AWS_S3_REGION_NAME = (
    os.getenv("S3_REGION") or os.getenv("AWS_S3_REGION_NAME") or "us-east-1"
).strip()
AWS_S3_ENDPOINT_URL = (
    os.getenv("S3_ENDPOINT") or os.getenv("AWS_S3_ENDPOINT_URL") or ""
).strip() or None
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN", "").strip() or None
AWS_LOCATION = os.getenv("AWS_LOCATION", "media").strip() or "media"

_force_path_style = (
    os.getenv("S3_FORCE_PATH_STYLE", "false").strip().lower()
    in {"1", "true", "yes"}
)
_force_s3 = os.getenv("USE_S3", "").strip().lower() in {"1", "true", "yes"}
_env_wants_s3 = ENVIRONMENT in {"production", "testing"}
_has_s3_credentials = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)

USE_S3_MEDIA = bool(AWS_STORAGE_BUCKET_NAME) and _has_s3_credentials and (
    _force_s3 or _env_wants_s3 or bool(AWS_S3_ENDPOINT_URL)
)

if USE_S3_MEDIA:
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = (
        os.getenv("AWS_QUERYSTRING_AUTH", "True").strip().lower()
        in {"1", "true", "yes"}
    )
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_ADDRESSING_STYLE = "path" if _force_path_style else "auto"
    AWS_S3_OBJECT_PARAMETERS = {
        "CacheControl": "max-age=86400",
    }

    _s3_options = {
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "access_key": AWS_ACCESS_KEY_ID,
        "secret_key": AWS_SECRET_ACCESS_KEY,
        "region_name": AWS_S3_REGION_NAME,
        "default_acl": AWS_DEFAULT_ACL,
        "querystring_auth": AWS_QUERYSTRING_AUTH,
        "file_overwrite": AWS_S3_FILE_OVERWRITE,
        "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        "signature_version": AWS_S3_SIGNATURE_VERSION,
        "location": AWS_LOCATION,
        "addressing_style": AWS_S3_ADDRESSING_STYLE,
    }
    if AWS_S3_ENDPOINT_URL:
        _s3_options["endpoint_url"] = AWS_S3_ENDPOINT_URL
    if AWS_S3_CUSTOM_DOMAIN:
        _s3_options["custom_domain"] = AWS_S3_CUSTOM_DOMAIN

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _s3_options,
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
    elif AWS_S3_ENDPOINT_URL:
        MEDIA_URL = (
            f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/"
            f"{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}/"
        )
    else:
        MEDIA_URL = (
            f"https://{AWS_STORAGE_BUCKET_NAME}.s3."
            f"{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION}/"
        )

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

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
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
    "gemini-3.5-flash-lite"
)

# Policy AI Model
GEMINI_POLICY_MODEL = os.getenv(
    "GEMINI_POLICY_MODEL",
    "gemini-3.5-flash-lite"
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

# Optional shared secret for POST /expenses/email-ingest/
EMAIL_INGEST_SECRET = os.getenv("EMAIL_INGEST_SECRET", "")

# Free-tier friendly: poll IMAP inside the web process (no Celery worker needed).
EMAIL_IMAP_POLL_ENABLED = (
    os.getenv("EMAIL_IMAP_POLL_ENABLED", "False").lower() == "true"
)
EMAIL_IMAP_POLL_INTERVAL_SECONDS = int(
    os.getenv("EMAIL_IMAP_POLL_INTERVAL_SECONDS", "30")
)


# --------------------------------------------------
# CELERY
# --------------------------------------------------

# --------------------------------------------------
# CELERY
# --------------------------------------------------

from celery.schedules import crontab


CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    ),
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    ),
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


# --------------------------------------------------
# CELERY BEAT SCHEDULE
# --------------------------------------------------

CELERY_BEAT_SCHEDULE = {

    # Check reimbursement mailbox every minute
    "fetch-reimbursement-emails": {
        "task": "expenses.tasks.fetch_emails_task",
        "schedule": 60.0,
    },

    # External database synchronization - 2:00 AM IST
    "scheduled-external-database-sync-every-night": {
        "task": (
            "tenants.tasks."
            "scheduled_external_database_sync"
        ),
        "schedule": crontab(
            hour=2,
            minute=0,
        ),
    },
}

BAMBOOHR_CLIENT_ID = os.getenv("BAMBOOHR_CLIENT_ID")
BAMBOOHR_CLIENT_SECRET = os.getenv("BAMBOOHR_CLIENT_SECRET")

RIPPLING_CLIENT_ID = os.getenv("RIPPLING_CLIENT_ID")
RIPPLING_CLIENT_SECRET = os.getenv("RIPPLING_CLIENT_SECRET")

ADP_CLIENT_ID = os.getenv("ADP_CLIENT_ID")
ADP_CLIENT_SECRET = os.getenv("ADP_CLIENT_SECRET")

WORKDAY_CLIENT_ID = os.getenv("WORKDAY_CLIENT_ID")
WORKDAY_CLIENT_SECRET = os.getenv("WORKDAY_CLIENT_SECRET")

QUICKBOOKS_CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID")
QUICKBOOKS_CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET")

IMAP_ENCRYPTION_KEY = os.getenv(
    "IMAP_ENCRYPTION_KEY"
)

INTEGRATION_ENCRYPTION_KEY = os.getenv(
    "INTEGRATION_ENCRYPTION_KEY"
)

def _sanitize_fernet_key(name, value):
    """Accept only real Fernet keys; otherwise derive a stable valid key."""
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    raw = (value or "").strip()
    if raw:
        try:
            Fernet(raw.encode("utf-8"))
            return raw
        except (ValueError, TypeError):
            pass
    secret = os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "zepex-dev"
    return base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}:{secret}".encode("utf-8")).digest()
    ).decode("ascii")


IMAP_ENCRYPTION_KEY = _sanitize_fernet_key(
    "IMAP_ENCRYPTION_KEY",
    IMAP_ENCRYPTION_KEY,
)
INTEGRATION_ENCRYPTION_KEY = _sanitize_fernet_key(
    "INTEGRATION_ENCRYPTION_KEY",
    INTEGRATION_ENCRYPTION_KEY,
)
CELERY_BEAT_SCHEDULER = (
    "django_celery_beat.schedulers:"
    "DatabaseScheduler"
)

QUICKBOOKS_CLIENT_ID = os.getenv(
    "QUICKBOOKS_CLIENT_ID"
)

QUICKBOOKS_CLIENT_SECRET = os.getenv(
    "QUICKBOOKS_CLIENT_SECRET"
)

QUICKBOOKS_REDIRECT_URI = os.getenv(
    "QUICKBOOKS_REDIRECT_URI"
)

QUICKBOOKS_ENVIRONMENT = os.getenv(
    "QUICKBOOKS_ENVIRONMENT",
    "sandbox",
)