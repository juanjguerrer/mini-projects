"""
Notify via ntfy.sh when a page stops showing its maintenance message.

Config (environment variables):
    NTFY_TOPIC  required, your ntfy topic (keep it secret)
    PAGE_URL    optional, page to check
    MARKER      optional, text shown while the page is down

Runs a single check per execution. Schedule it with cron / GitHub Actions.
"""
import os
import yaml
import requests
import ssl
import pathlib
from requests.adapters import HTTPAdapter
from typing import Literal
from pathlib import Path

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
CheckType = Literal["marker_absent", "changed", "marker_present"]

class LegacyTLSAdapter(HTTPAdapter):
    """Allow servers with older TLS settings that OpenSSL 3.0+ rejects by default."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

def read_yaml_config(file_path: str | Path) -> dict:
    """Read configuration from a YAML file."""
    # Read from __file__ using pathlib
    file_path = pathlib.Path(__file__).parent / file_path
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            if not isinstance(config, dict) or "pages" not in config:
                raise ValueError("Invalid configuration format. Expected a dictionary with a 'pages' key.")
            return config
    except FileNotFoundError:
        print(f"Configuration file {file_path} not found.")
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return {}

def check_page(url: str, check_type: CheckType, marker: str | None = None) -> bool:
    if check_type not in ["marker_absent", "changed", "marker_present"]:
        raise ValueError(f"Invalid check_type: {check_type}. Must be one of 'marker_absent', 'changed', or 'marker_present'.")
    """Check the page for availability based on the specified type."""
    try:
        with requests.Session() as session:
            session.mount("https://", LegacyTLSAdapter())
            r = session.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return False
    if r.status_code != 200:
        print(f"Page returned status code {r.status_code}.")
        return False
    if check_type == "changed":
        # Implement logic to check if the page content has changed
        # This is a placeholder; actual implementation may vary
        return True

    if marker is None:
        print("Marker must be provided for marker_absent or marker_present checks.")
        return False

    found = marker.lower() in r.text.lower()
    return found if check_type == "marker_present" else not found

def notify(url: str) -> None:
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=f"Page {url} is available!", timeout=20)


if __name__ == "__main__":
    config = read_yaml_config("config.yaml")
    for page in config.get("pages", []):
        url = page.get("url")
        if not url:
            print("URL is required for each page. Skipping.")
            continue
        check_type = page.get("check_type", "marker_absent")
        marker = page.get("marker")
        if check_type in ["marker_absent", "marker_present"] and "marker" not in page:
            print(f"Marker is required for check_type '{check_type}' for page {url}. Skipping.")
            continue
        if check_page(url, check_type, marker):
            notify(url)
            print(f"Page {url} is available, notification sent.")
        else:
            print(f"Page {url} is still unavailable.")