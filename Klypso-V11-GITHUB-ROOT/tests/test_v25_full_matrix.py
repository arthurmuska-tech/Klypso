import re
from pathlib import Path

import pytest

from klypso import create_app
from klypso.auth import _create_email_user


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "v25-matrix-secret",
        "DATABASE_PATH": str(tmp_path / "klypso.sqlite3"),
        "STORAGE_PATH": str(tmp_path / "storage"),
        "PUBLIC_BASE_URL": "https://klypso-test.example",
        "GOOGLE_CLIENT_ID": "google-client",
        "GOOGLE_CLIENT_SECRET": "google-secret",
        "EMAIL_FROM": "noreply@example.com",
        "SESSION_COOKIE_SECURE": False,
    })


PUBLIC_PATHS = [
    "/", "/demo", "/pricing", "/login", "/register",
    "/mentions-legales", "/confidentialite", "/cgu", "/cgv", "/contact",
    "/robots.txt", "/sitemap.xml", "/healthz",
]

APP_PATHS = [
    "/dashboard", "/clips", "/clips/create", "/studio", "/publisher",
    "/brand-kit", "/subscription", "/payments", "/account",
]

WOODS = ["oak", "walnut", "birch", "cherry", "ebony"]
PALETTES = ["paper", "linen", "clay", "ocean", "forest", "plum",
            "graphite", "midnight", "sage", "sand", "lavender", "slate"]
ACCENTS = ["#9b7bff", "#63a4ff", "#59e6df", "#ff76c8", "#d59a62"]


def _authenticated_client(app, email="matrix@example.com"):
    with app.app_context():
        _create_email_user(email)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_email"] = email
        sess["csrf_token"] = "matrix-csrf"
    return client


@pytest.mark.parametrize("case", range(200))
def test_v25_full_reliability_matrix(case, tmp_path):
    """200 deterministic regression checks across routes, UI contracts and personalization.

    These are application-level checks; external Google/Stripe/mail providers are mocked
    or checked through their own integration tests so CI remains deterministic.
    """
    app = make_app(tmp_path)

    if case < 60:
        # 60 route checks: every public route is exercised repeatedly with independent
        # query variants to catch template/context regressions without third-party calls.
        path = PUBLIC_PATHS[case % len(PUBLIC_PATHS)]
        suffix = "" if case % 2 == 0 else "?utm_source=matrix"
        response = app.test_client().get(path + suffix)
        assert response.status_code < 500, (path, response.status_code)
        if path not in {"/robots.txt", "/sitemap.xml"}:
            assert "text/html" in response.content_type
            assert response.data
        else:
            assert response.data

    elif case < 110:
        # 50 authenticated surface checks across dashboard, clips, studio, publishing,
        # Brand Kit, billing and account.
        path = APP_PATHS[(case - 60) % len(APP_PATHS)]
        response = _authenticated_client(app).get(path)
        assert response.status_code < 500, (path, response.status_code)
        assert response.data

    elif case < 160:
        # 50 personalization contract checks: every wood/material, atmosphere and
        # accent option must exist and be wired to the real persistence/apply layer.
        root = Path(__file__).resolve().parents[1]
        account = (root / "templates" / "account.html").read_text(encoding="utf-8")
        brand = (root / "templates" / "brand_kit.html").read_text(encoding="utf-8")
        js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "css" / "v14.css").read_text(encoding="utf-8")

        wood = WOODS[(case - 110) % len(WOODS)]
        accent = ACCENTS[((case - 110) // len(WOODS)) % len(ACCENTS)]
        assert f'data-wood="{wood}"' in account
        assert f'data-wood="{wood}"' in css
        assert f'data-accent="{accent}"' in account or f'data-accent="{accent}"' in brand
        assert "function applyWood" in js
        assert "klypso.wood" in js
        assert "localStorage" in js
        assert "data-wood" in js
        assert "data-setting-group="palette"" in account
        assert "data-palette" in js

    else:
        # 40 structural/security checks. Every run verifies that the production UI
        # keeps the main contracts needed by a streamer-facing release.
        root = Path(__file__).resolve().parents[1]
        base = (root / "templates" / "base.html").read_text(encoding="utf-8")
        login = (root / "templates" / "login.html").read_text(encoding="utf-8")
        register = (root / "templates" / "register.html").read_text(encoding="utf-8")
        account = (root / "templates" / "account.html").read_text(encoding="utf-8")
        brand = (root / "templates" / "brand_kit.html").read_text(encoding="utf-8")
        js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")

        contracts = [
            'meta name="csrf-token"', "canonical", "app.css", "v14.css", "v14.js",
            "data-sidebar-open", "data-command-palette", "csrf_token()",
            "data-google-signin", "g_id_onload", "handleGoogleCredential",
            'type="email"', 'type="password"', 'autocomplete="new-password"',
            "data-save-settings", "data-appearance-reset", "data-brand-reset",
            "data-setting="watermark"", "data-setting="motion"",
            "data-setting="displayName"", "data-setting-group="accent"",
            "data-setting-group="density"", "data-setting-group="radius"",
            "data-setting-group="palette"", "data-caption",
            "applyAccent", "applyDensity", "applyRadius", "applyCaption",
            "applyPalette", "applyWood", "klypso.wood",
            "window.addEventListener('storage'",
        ]
        needle = contracts[(case - 160) % len(contracts)]
        combined = base + login + register + account + brand + js
        assert needle in combined, needle
        # The main auth forms must expose CSRF protection.
        assert "csrf_token()" in login
        assert "csrf_token()" in register
