"""Django settings for the news aggregator web app."""

import os
from pathlib import Path

import dj_database_url
import django_stubs_ext
from dotenv import load_dotenv

django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent
# override=True so edited .env values apply after a process restart
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production",
)

# Shared bearer token for /api/internal/* (Lambdas). Empty disables those routes (503).
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "").strip()

# SQS queue for new feed items → news_parser (empty = ingest dedups but does not enqueue).
FEED_ITEMS_QUEUE_URL = os.environ.get("FEED_ITEMS_QUEUE_URL", "").strip()

# Sync-invoked news_chat Lambda (empty + DEBUG → local stub response).
NEWS_CHAT_FUNCTION_NAME = os.environ.get("NEWS_CHAT_FUNCTION_NAME", "").strip()
AWS_REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or os.environ.get("BEDROCK_REGION")
    or "eu-central-1"
)

DEBUG = os.environ.get("DEBUG", "true").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "news.apps.NewsConfig",
]

MIDDLEWARE = [
    "config.middleware.ViewerHostMiddleware",  # before SecurityMiddleware
    "config.middleware.NormalizeTrailingSlashMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# Set from X-Viewer-Host by ViewerHostMiddleware (CloudFront cannot set X-Forwarded-Host).
USE_X_FORWARDED_HOST = True

# Lambda Function URL / some proxies can present paths without a trailing slash while the
# browser requested one. APPEND_SLASH then 301s to the slashed URL → infinite loop.
# Prefer in-process rewrite (NormalizeTrailingSlashMiddleware) over HTTP redirects.
APPEND_SLASH = False

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

_default_db = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
_db_url = os.environ.get("DATABASE_URL", _default_db)
# Lambda: no persistent connections across freezes; local/long-lived: reuse.
_conn_max_age = 0 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 600
DATABASES = {
    "default": dj_database_url.parse(
        _db_url,
        conn_max_age=_conn_max_age,
        ssl_require=_db_url.startswith("postgres")
        and os.environ.get("DATABASE_SSL", "true").lower() in ("1", "true", "yes"),
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Django admin / createsuperuser only
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1

# End users sign in only via Google — no local password accounts in the UI.
SOCIALACCOUNT_ONLY = True
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_LOGOUT_ON_GET = False

_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
if not _GOOGLE_CLIENT_ID or not _GOOGLE_CLIENT_SECRET:
    import warnings

    warnings.warn(
        "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing — "
        "put them in web/.env and fully restart the Django server "
        "(code reload does not pick up .env changes).",
        stacklevel=1,
    )

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": _GOOGLE_CLIENT_ID,
                "secret": _GOOGLE_CLIENT_SECRET,
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "google_login"
# Popup-done closes the OAuth window (or redirects to brief if not a popup).
LOGIN_REDIRECT_URL = "oauth_popup_done"
LOGOUT_REDIRECT_URL = "landing"
ACCOUNT_LOGOUT_REDIRECT_URL = "landing"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Force https in allauth absolute URLs even if proxy headers are missing.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = (
    "https" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or not DEBUG else "http"
)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
