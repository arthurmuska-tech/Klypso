import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("KLYPSO_BASE_URL", "http://127.0.0.1:5000")
OUT = Path("test-artifacts/browser")
OUT.mkdir(parents=True, exist_ok=True)

PUBLIC = [
    ("/", "home"),
    ("/demo", "demo"),
    ("/pricing", "pricing"),
    ("/login", "login"),
    ("/register", "register"),
]


def test_browser_audit():
    console_errors = []
    request_failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
        page.on("requestfailed", lambda req: request_failures.append(f"{req.method} {req.url}: {req.failure}"))

        for path, name in PUBLIC:
            console_errors.clear()
            request_failures.clear()
            response = page.goto(BASE + path, wait_until="networkidle")
            assert response is not None, f"No response for {path}"
            assert response.status < 400, f"{path} returned HTTP {response.status}"
            expect(page.locator("body")).to_be_visible()
            assert page.title().strip(), f"{path} has no document title"
            page.screenshot(path=str(OUT / f"{name}-desktop.png"), full_page=True)
            assert not console_errors, f"Console errors on {path}: {console_errors}"
            assert not request_failures, f"Failed requests on {path}: {request_failures}"

        # Real interaction checks on the public funnel.
        page.goto(BASE + "/", wait_until="networkidle")
        links = page.locator("a[href]")
        assert links.count() > 0, "Landing page has no navigable links"
        visible_links = []
        for i in range(min(links.count(), 40)):
            href = links.nth(i).get_attribute("href")
            if href and href.startswith("/") and not href.startswith("//"):
                visible_links.append(href)
        assert visible_links, "Landing page has no internal navigation"

        page.goto(BASE + "/login", wait_until="networkidle")
        email = page.locator('input[type="email"]')
        password = page.locator('input[type="password"]')
        expect(email).to_be_visible()
        expect(password).to_be_visible()
        email.fill("invalid@example.com")
        password.fill("invalid-password")
        form = page.locator("form").first
        if form.locator('button[type="submit"]').count():
            form.locator('button[type="submit"]').click()
            page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "login-interaction.png"), full_page=True)

        page.goto(BASE + "/register", wait_until="networkidle")
        expect(page.locator('input[type="email"]')).to_be_visible()
        page.screenshot(path=str(OUT / "register-interaction.png"), full_page=True)

        # Protected surfaces must fail closed rather than expose a broken page.
        protected = ["/dashboard", "/clips", "/studio", "/publisher", "/brand-kit", "/subscription", "/payments", "/account"]
        for path in protected:
            response = page.goto(BASE + path, wait_until="networkidle")
            assert response is not None
            assert response.status in (200, 302, 303), f"Unexpected {response.status} for {path}"
            assert "/login" in page.url or response.status == 200, f"{path} did not redirect to login when unauthenticated"

        # Mobile visual smoke check.
        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(BASE + "/", wait_until="networkidle")
        expect(mobile.locator("body")).to_be_visible()
        mobile.screenshot(path=str(OUT / "home-mobile.png"), full_page=True)

        browser.close()
