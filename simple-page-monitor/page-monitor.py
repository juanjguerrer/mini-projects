"""
Notify via ntfy.sh when a monitored page reaches the state you are waiting for.

Pages are listed in config.yaml. Each page has a check_type:
    marker_absent   notify when the marker text is no longer on the page
    marker_present  notify when the marker text appears on the page
    changed         notify when the page content changes (hashes kept in state.json)

Environment variables:
    NTFY_TOPIC  required, your ntfy topic (keep it secret)

Runs a single check per execution. Schedule it with cron / GitHub Actions.
"""

import dataclasses
import json
import os
import ssl
import sys
from hashlib import sha256
from pathlib import Path
from typing import Literal

import requests
import yaml
from requests.adapters import HTTPAdapter

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


@dataclasses.dataclass(frozen=True)
class Notification:
    should_notify: bool
    hash_to_save: str | None = None
    message: str | None = None


@dataclasses.dataclass(frozen=True)
class PageData:
    name: str
    url: str
    check_type: CheckType = "marker_absent"
    marker: str | None = None
    message: str | None = None


def read_yaml_config(file_path: str | Path) -> list[PageData]:
    """Read configuration from a YAML file."""
    # Read from __file__ using pathlib
    file_path = Path(__file__).parent / file_path
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
            if not isinstance(config, dict) or "pages" not in config:
                raise ValueError(
                    "Invalid configuration format. Expected a dictionary with a 'pages' key."
                )
            return [PageData(**page) for page in config.get("pages", [])]
    except FileNotFoundError:
        print(f"Configuration file {file_path} not found.")
        raise FileNotFoundError("Configuration file not found.")
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        raise ValueError("Error parsing YAML file.")


def get_message(page: PageData) -> str:
    """Return the message to be sent in the notification."""
    if page.message:
        return page.message
    if page.check_type == "marker_absent":
        return f"Marker '{page.marker}' is absent on page {page.url}."
    elif page.check_type == "marker_present":
        return f"Marker '{page.marker}' is present on page {page.url}."
    elif page.check_type == "changed":
        return f"Page {page.url} has changed."
    else:
        return f"Page {page.url} status unknown."


def check_page(page: PageData) -> Notification:
    """Check the page for availability based on the specified type."""
    if page.check_type not in ["marker_absent", "changed", "marker_present"]:
        raise ValueError(
            f"Invalid check_type: {page.check_type}. Must be one of 'marker_absent', 'changed', or 'marker_present'."
        )
    try:
        with requests.Session() as session:
            session.mount("https://", LegacyTLSAdapter())
            r = session.get(page.url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return Notification(should_notify=False)
    if r.status_code != 200:
        print(f"Page returned status code {r.status_code}.")
        return Notification(should_notify=False)
    if page.check_type == "changed":
        current_hash = hash_content(r.text)
        state = open_state_file()
        previous_hash = state.get(page.url)
        if previous_hash is None:
            print("No previous hash found. Saving current hash.")
            return Notification(should_notify=False, hash_to_save=current_hash)
        elif previous_hash == current_hash:
            print("Page content has not changed.")
            return Notification(should_notify=False)
        else:
            return Notification(
                should_notify=True, hash_to_save=current_hash, message=get_message(page)
            )

    if page.marker is None:
        print("Marker must be provided for marker_absent or marker_present checks.")
        return Notification(should_notify=False)

    found = page.marker.lower() in r.text.lower()
    result = False
    if (page.check_type == "marker_absent" and not found) or (
        page.check_type == "marker_present" and found
    ):
        result = True
    return (
        Notification(should_notify=True, message=get_message(page))
        if result
        else Notification(should_notify=False)
    )


def open_state_file() -> dict:
    """Open the state.json file and return its contents as a dictionary."""
    file_path = Path(__file__).parent / "state.json"
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state_file(state: dict) -> None:
    """Save the given state dictionary to state.json."""
    file_path = Path(__file__).parent / "state.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def notify(notification: Notification) -> None:
    """Send a notification via ntfy.sh."""
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}", data=notification.message, timeout=20
    )
    response.raise_for_status()


def hash_content(content: str) -> str:
    """Return a hash of the content for change detection."""
    return sha256(content.encode("utf-8")).hexdigest()


def save_hash(page_url: str, content_hash: str) -> None:
    """Save the hash of the page content to state.json for future comparison."""
    state = open_state_file()
    state[page_url] = content_hash
    save_state_file(state)


def main():
    has_errors = False
    config = read_yaml_config("config.yaml")
    for page in config:
        url = page.url
        check_type = page.check_type
        marker = page.marker
        if check_type in ["marker_absent", "marker_present"] and marker is None:
            print(
                f"Marker is required for check_type '{check_type}' for page {url}. Skipping."
            )
            continue
        notification = check_page(page)

        try:
            if notification.should_notify:
                notify(notification)
                print(f"Notification sent for page {url}.")
            else:
                print(f"No notification needed for page {url}.")
            if notification.hash_to_save:
                save_hash(url, notification.hash_to_save)
        except requests.RequestException as e:
            print(f"Error sending notification: {e}")
            has_errors = True
    if has_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
