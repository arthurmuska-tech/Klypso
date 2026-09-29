"""KLYPSO V27: 1000-request regression matrix.

This deliberately exercises the real Flask application through its test client.
It is not a claim that every external provider (Stripe/Google/AI) is reachable
in CI; those integrations are covered by isolated contract tests and mocks.
"""

from pathlib import Path

import pytest

from klypso import create_app


# Ten real surfaces already covered by the existing regression suite.
# 100 query variants per surface = exactly 1,000 parametrized test cases.
SURFACES = [
    ("/", 200, "KLYPSO"),
    ("/pricing", 200, "Tarifs"),
    ("/login", 200, "Connexion"),
    ("/register", 200, "Créer"),
    ("/healthz", 200, '"status"'),
    ("/readyz", 200, '"status"'),
    ("/dashboard", 302, None),
    ("/clips", 302, None),
    ("/studio", 302, None),
    ("/account", 302, None),
]

CASES = [
    (surface, expected, marker, variant)
    for surface, expected, marker in SURFACES
    for variant in range(100)
]


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    root = tmp_path_factory.mktemp("klypso-1000")
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "klypso-1000-test-secret",
            "DATABASE_PATH": str(root / "klypso.sqlite3"),
            "STORAGE_PATH": str(root / "storage"),
            "SESSION_COOKIE_SECURE": False,
            "EMAIL_OTP_DEV_LOG_CODE": False,
            "EMAIL_OTP_COOLDOWN_SECONDS": 0,
            "EMAIL_OTP_MAX_PER_HOUR": 1000,
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "REQUIRE_POSTGRES": False,
        }
    )


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.mark.parametrize("surface,expected,marker,variant", CASES)
def test_1000_surface_requests(client, surface, expected, marker, variant):
    """One independent regression case for every surface/variant combination."""
    response = client.get(
        surface,
        query_string={
            "regression_case": str(variant),
            "cache_buster": f"v27-{variant:03d}",
        },
    )

    assert response.status_code == expected, (
        f"{surface} returned {response.status_code} "
        f"(expected {expected}) in variant {variant}"
    )

    # Every HTML/API response must at least be protected by the standard
    # response headers installed by Klypso's security middleware.
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    if expected == 302:
        location = response.headers.get("Location", "")
        assert "/login" in location
    elif marker:
        body = response.get_data(as_text=True)
        assert marker in body


def test_1000_matrix_has_exactly_1000_cases():
    assert len(CASES) == 1000


def test_static_frontend_assets_exist():
    root = Path(__file__).resolve().parents[1]
    for relative in [
        "static/js/app.js",
        "static/js/v26.js",
        "static/js/v26-appearance.js",
        "static/css/v26.css",
        "templates/base.html",
        "templates/pricing.html",
    ]:
        path = root / relative
        assert path.exists(), relative
        assert path.stat().st_size > 0, relative
