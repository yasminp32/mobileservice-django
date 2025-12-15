import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))
print("DEBUG SETTINGS.ZOHO_CLIENT_ID =", os.getenv("ZOHO_CLIENT_ID"))

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
DEBUG = os.getenv("DEBUG", "1") == "1"
#ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".ngrok-free.dev",
     ".loclx.io",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = True


CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5173",
    "https://ce8beda6663d.ngrok-free.app",
]

CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_CREDENTIALS = True
#print("LOADED ALLOWED_HOSTS =", ALLOWED_HOSTS)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "core",
    "zoho_integration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mobileservice.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "mobileservice.wsgi.application"

# Database (expects a DATABASE_URL like postgresql://user:pass@host:5432/dbname)
def parse_db_url(url):
    if not url:
        return None
    u = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": u.path.lstrip("/"),
        "USER": u.username or "",
        "PASSWORD": u.password or "",
        "HOST": u.hostname or "localhost",
        "PORT": str(u.port or 5432),
    }

DATABASES = {
    "default": parse_db_url(os.getenv("DATABASE_URL")) or {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "mobileshopdb",
        "USER": "postgres",
        "PASSWORD": "4921",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny"
    ]
}

# Auto-assign settings
ASSIGN_RADIUS_KM = float(os.getenv("ASSIGN_RADIUS_KM", "25"))
GEO_COUNTRY = os.getenv("GEO_COUNTRY", "IN")

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = "yasminp32@gmail.com"
EMAIL_HOST_PASSWORD = "npfl ltck khno gqkr"  # NOT your Gmail password

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
# =========================
# ZOHO BOOKS CONFIGURATION
# =========================

ZOHO_AUTH_BASE_URL = os.getenv("ZOHO_AUTH_BASE_URL", "https://accounts.zoho.in/oauth/v2")
ZOHO_BOOKS_BASE_URL = os.getenv("ZOHO_BOOKS_BASE_URL", "https://www.zohoapis.in/books/v3")
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI")
ZOHO_BOOKS_ORGANIZATION_ID = os.getenv("ZOHO_BOOKS_ORGANIZATION_ID","60059687124")

ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ZOHO_BOOKS_ACCESS_TOKEN = os.getenv("ZOHO_BOOKS_ACCESS_TOKEN")



ZOHO_PURCHASE_ACCOUNT_ID = os.getenv("ZOHO_PURCHASE_ACCOUNT_ID")
ZOHO_SALES_ACCOUNT_ID = os.getenv("ZOHO_SALES_ACCOUNT_ID", "")
ZOHO_SERVICE_INCOME_ACCOUNT_ID = os.getenv("ZOHO_SERVICE_INCOME_ACCOUNT_ID", "")
ZOHO_COGS_ACCOUNT_ID = os.getenv("ZOHO_COGS_ACCOUNT_ID", "")
ZOHO_OTHER_INCOME_ACCOUNT_ID = os.getenv("ZOHO_OTHER_INCOME_ACCOUNT_ID", "")

