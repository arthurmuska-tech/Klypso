import pytest

from klypso import create_app
from klypso.auth import _create_email_user
from klypso.database import get_db


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "stripe-test-secret",
            "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
            "STORAGE_PATH": str(tmp_path / "storage"),
            "SESSION_COOKIE_SECURE": False,
            "STRIPE_TRIAL_DAYS": 10,
            "STRIPE_SECRET_KEY": "",
            "STRIPE_WEBHOOK_SECRET": "",
            "STRIPE_PRO_PRICE_ID": "",
            "STRIPE_ULTRA_PRICE_ID": "",
            "STRIPE_PRO_ANNUAL_PRICE_ID": "",
            "STRIPE_ULTRA_ANNUAL_PRICE_ID": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "REQUIRE_POSTGRES": False,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def login_user(app, client, email="stripe@example.com"):
    with app.app_context():
        user = _create_email_user(email)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]
        sess["csrf_token"] = "csrf-ok"
    return user


def test_pricing_uses_configured_trial_days(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "10 JOURS" in response.get_data(as_text=True)
    assert "14 JOURS" not in response.get_data(as_text=True)


def test_checkout_requires_authentication(client):
    response = client.post("/billing/checkout", data={"plan": "pro"})
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_checkout_requires_cgv(app, client):
    login_user(app, client)
    response = client.post(
        "/billing/checkout",
        data={"plan": "pro", "billing_interval": "monthly", "csrf_token": "csrf-ok"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/pricing")


def test_checkout_fails_cleanly_without_stripe_keys(app, client):
    login_user(app, client, "stripe-missing@example.com")
    response = client.post(
        "/billing/checkout",
        data={
            "plan": "ultra",
            "billing_interval": "monthly",
            "accept_cgv": "on",
            "csrf_token": "csrf-ok",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/pricing")


def test_portal_fails_cleanly_without_stripe_key(app, client):
    login_user(app, client, "portal@example.com")
    response = client.post("/billing/portal", data={"csrf_token": "csrf-ok"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/subscription")


def test_webhook_reports_not_configured_without_secret(client):
    response = client.post("/billing/webhook", data=b"{}")
    assert response.status_code == 503


def test_webhook_rejects_bad_signature(app, client):
    app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    response = client.post(
        "/billing/webhook",
        data=b'{"id":"evt_test","type":"checkout.session.completed","data":{"object":{}}}',
        headers={"Stripe-Signature": "invalid"},
    )
    assert response.status_code == 400


def test_stripe_customer_column_exists(app):
    with app.app_context():
        user = _create_email_user("customer-column@example.com")
        with get_db(app.config["DATABASE_PATH"]) as db:
            row = db.execute(
                "SELECT stripe_customer_id FROM users WHERE id=?",
                (user["id"],),
            ).fetchone()
    assert row is not None
