"""
Notify via ntfy.sh when a page stops showing its maintenance message.

Config (environment variables):
    NTFY_TOPIC  required, your ntfy topic (keep it secret)
    PAGE_URL    optional, page to check
    MARKER      optional, text shown while the page is down

Runs a single check per execution. Schedule it with cron / GitHub Actions.
"""
import os

import requests

URL = os.environ.get("PAGE_URL", "https://siurp.sep.gob.mx")
MARKER = os.environ.get("MARKER", "estamos trabajando para mejorar nuestro servicio").lower()
NTFY_TOPIC = os.environ["NTFY_TOPIC"]


def available() -> bool:
    try:
        r = requests.get(URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return False
    return r.status_code == 200 and MARKER not in r.text.lower()


def notify() -> None:
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=f"Page {URL} is available!", timeout=20)


if __name__ == "__main__":
    if available():
        notify()
        print("Available, notification sent.")
    else:
        print("Still unavailable.")