"""
Django settings for the Intelligent Deepfake Detection & Multimedia
Verification platform.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

_env_path = BASE_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# --------------------------------------------------------------
# Core
# --------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.environ.get("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
SERVER_PUBLIC_HOST = os.environ.get("SERVER_PUBLIC_HOST", "")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "accounts",
    "detection",
    "adminpanel",
    "billing",
    "support",
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
]

ROOT_URLCONF = "deepfake_platform.urls"

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

WSGI_APPLICATION = "deepfake_platform.wsgi.application"

# --------------------------------------------------------------
# Database
# --------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --------------------------------------------------------------
# Custom auth
# --------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "accounts:landing"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --------------------------------------------------------------
# I18N / TZ
# --------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------
# Static & media
# --------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

UPLOAD_DIR = str(MEDIA_ROOT / "uploads")
REPORT_DIR = str(MEDIA_ROOT / "reports")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

MAX_UPLOAD_SIZE_MB = 16
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------
# Default admin account (bootstrapped after migrate, see accounts/apps.py)
# --------------------------------------------------------------
DEFAULT_ADMIN_NAME = os.environ.get("ADMIN_NAME", "Administrator")
DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower().strip()
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")

# --------------------------------------------------------------
# Email / OTP
# --------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "").strip() or SMTP_USERNAME

EMAIL_CONFIGURED = bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD)

if EMAIL_CONFIGURED:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = SMTP_HOST
    EMAIL_PORT = SMTP_PORT
    EMAIL_HOST_USER = SMTP_USERNAME
    EMAIL_HOST_PASSWORD = SMTP_PASSWORD
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = SMTP_FROM_EMAIL
else:
    # DEV MODE: OTPs are printed to console + shown on-screen instead of emailed
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "noreply@deepfake-platform.local"

OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", "10") or 10)

# --------------------------------------------------------------
# ML model
# --------------------------------------------------------------
MODEL_PATH = str(BASE_DIR / "ml_model" / "best_image_deepfake_model.keras")
IMG_SIZE = 224
MODEL_NAME = "EfficientNetB0 (fine-tuned)"
MODEL_ACCURACY = "91.02%"
MODEL_ROC_AUC = "0.9805"

VIDEO_MODEL_PATH = str(BASE_DIR / "ml_model" / "video_model.keras")
VIDEO_MODEL_NAME = "EfficientNetB0 (fine-tuned on FaceForensics++ C23)"
VIDEO_MODEL_THRESHOLD = "0.62 (fake probability)"

AUDIO_MODEL_PATH = str(BASE_DIR / "ml_model" / "audio_model.keras")
AUDIO_MODEL_NAME = "CNN (Log-Mel Spectrogram Classifier)"
AUDIO_MODEL_ACCURACY = "99.93%"
AUDIO_MODEL_ROC_AUC = "1.0000"

TEXT_MODEL_PATH = str(BASE_DIR / "ml_model" / "text_model.pkl")
TEXT_VECTORIZER_PATH = str(BASE_DIR / "ml_model" / "text_vectorizer.pkl")
TEXT_MODEL_NAME = "TF-IDF + Logistic Regression"
TEXT_MODEL_ACCURACY = "100.00% (test set)"
TEXT_MODEL_ROC_AUC = "1.0000"

# --------------------------------------------------------------
# Billing / paywall
# --------------------------------------------------------------
FREE_DETECTION_LIMIT = int(os.environ.get("FREE_DETECTION_LIMIT", "5") or 5)
PAID_ACCESS_DAYS = int(os.environ.get("PAID_ACCESS_DAYS", "7") or 7)
PAID_ACCESS_PRICE_INR = int(os.environ.get("PAID_ACCESS_PRICE_INR", "100") or 100)

# Manual UPI payment verification: the admin's real UPI ID, shown as a
# QR code on the paywall page. Users pay directly to this UPI ID (no
# payment gateway, no fees, no KYC), then submit their transaction
# reference number for an admin to manually approve in the admin panel.
UPI_ID = os.environ.get("UPI_ID", "").strip()
UPI_PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "VeriScan AI").strip()

# --------------------------------------------------------------
# Session
# --------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 1 week
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
