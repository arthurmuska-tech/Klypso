import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "data" / "klypso.sqlite3"))
    STORAGE_PATH = os.environ.get("STORAGE_PATH", str(BASE_DIR / "storage"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "512")) * 1024 * 1024

    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", FLASK_ENV == "production")
    SESSION_COOKIE_NAME = "klypso_session"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
    STRIPE_ULTRA_PRICE_ID = os.environ.get("STRIPE_ULTRA_PRICE_ID", "")
    STRIPE_PRO_ANNUAL_PRICE_ID = os.environ.get("STRIPE_PRO_ANNUAL_PRICE_ID", "")
    STRIPE_ULTRA_ANNUAL_PRICE_ID = os.environ.get("STRIPE_ULTRA_ANNUAL_PRICE_ID", "")
    STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "http://localhost:5000/subscription?success=1")
    STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/pricing?cancelled=1")
    STRIPE_PORTAL_RETURN_URL = os.environ.get("STRIPE_PORTAL_RETURN_URL", "http://localhost:5000/subscription")

    ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "")

    # Legal / publication settings. Unknown business facts intentionally stay empty.
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")
    LEGAL_ENTITY_NAME = os.environ.get("LEGAL_ENTITY_NAME", "")
    LEGAL_STATUS = os.environ.get("LEGAL_STATUS", "")
    LEGAL_ADDRESS = os.environ.get("LEGAL_ADDRESS", "")
    LEGAL_SIRET = os.environ.get("LEGAL_SIRET", "")
    LEGAL_RCS = os.environ.get("LEGAL_RCS", "")
    LEGAL_VAT = os.environ.get("LEGAL_VAT", "")
    LEGAL_PUBLICATION_DIRECTOR = os.environ.get("LEGAL_PUBLICATION_DIRECTOR", "")
    LEGAL_CONTACT_EMAIL = os.environ.get("LEGAL_CONTACT_EMAIL", "")
    LEGAL_CONTACT_PHONE = os.environ.get("LEGAL_CONTACT_PHONE", "")
    HOSTER_NAME = os.environ.get("HOSTER_NAME", "")
    HOSTER_ADDRESS = os.environ.get("HOSTER_ADDRESS", "")
    HOSTER_PHONE = os.environ.get("HOSTER_PHONE", "")
    PRIVACY_CONTACT_EMAIL = os.environ.get("PRIVACY_CONTACT_EMAIL", "")
    MEDIATOR_NAME = os.environ.get("MEDIATOR_NAME", "")
    MEDIATOR_ADDRESS = os.environ.get("MEDIATOR_ADDRESS", "")
    MEDIATOR_WEBSITE = os.environ.get("MEDIATOR_WEBSITE", "")
    ACCESSIBILITY_DECLARATION_ENABLED = env_bool("ACCESSIBILITY_DECLARATION_ENABLED", False)

    CGU_VERSION = os.environ.get("CGU_VERSION", "2026-09-26")
    PRIVACY_VERSION = os.environ.get("PRIVACY_VERSION", "2026-09-26")
    COOKIE_POLICY_VERSION = os.environ.get("COOKIE_POLICY_VERSION", "2026-09-26")

    PRO_MONTHLY_PRICE_EUR = os.environ.get("PRO_MONTHLY_PRICE_EUR", "12,99")
    ULTRA_MONTHLY_PRICE_EUR = os.environ.get("ULTRA_MONTHLY_PRICE_EUR", "29,99")
    PRO_ANNUAL_PRICE_EUR = os.environ.get("PRO_ANNUAL_PRICE_EUR", "")
    ULTRA_ANNUAL_PRICE_EUR = os.environ.get("ULTRA_ANNUAL_PRICE_EUR", "")
    PRICES_ARE_TTC = env_bool("PRICES_ARE_TTC", True)
