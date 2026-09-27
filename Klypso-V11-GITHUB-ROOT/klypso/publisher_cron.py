"""Render cron bridge for KLYPSO's distribution queue.

The cron job never opens the web service's local SQLite/storage directly.
It calls the public web service with a shared secret instead.
"""
import os
import sys

import requests


def main():
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    secret = os.getenv("KLYPSO_CRON_SECRET", "").strip()
    if not base or not secret:
        print("PUBLIC_BASE_URL and KLYPSO_CRON_SECRET are required.", file=sys.stderr)
        return 2

    response = requests.post(
        f"{base}/api/publisher/run-due",
        headers={"X-KLYPSO-CRON-KEY": secret},
        timeout=90,
    )
    print(response.text)
    if response.status_code >= 400:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
