# simple-page-monitor

A tiny script that checks one or more web pages and sends a push notification (via [ntfy.sh](https://ntfy.sh)) when a page reaches the state you are waiting for. I built it to know when a government site came back from maintenance, but it works for any page where a known message appears or disappears.

> This README was written with the help of [Claude](https://claude.ai) (Anthropic).

## How it works

1. Reads the list of pages from `config.yaml`.
2. Fetches each page. If it doesn't answer `200`, the page is treated as not ready.
3. Applies the page's `check_type` to the HTML (see below).
4. If the condition is met, sends a notification to your ntfy topic.

It runs a single check per execution. Scheduling is handled by GitHub Actions (every 6 hours) or any cron-like tool.

> Some sites return `200 OK` even while showing a maintenance message, so the script checks the page text, not just the status code.

## Configuration

### `config.yaml`

```yaml
pages:
  - name: SIURP SEP
    url: https://siurp.sep.gob.mx
    check_type: marker_absent
    marker: "estamos trabajando para mejorar nuestro servicio"
```

| Field        | Required                     | Description                                              |
|--------------|------------------------------|----------------------------------------------------------|
| `name`       | no                           | Label for the page.                                      |
| `url`        | yes                          | Page to check.                                           |
| `check_type` | no (default `marker_absent`) | When to notify. See the table below.                     |
| `marker`     | for marker checks            | Text to look for (case-insensitive).                     |

| `check_type`     | Notifies when...                                  | Status        |
|------------------|---------------------------------------------------|---------------|
| `marker_absent`  | the marker text is **no longer** on the page      | working       |
| `marker_present` | the marker text **appears** on the page           | working       |
| `changed`        | the page content changed since the last check     | working       |

> The first time a `changed` page is checked it only stores its hash in `state.json`; you get notified from the next change on.

The `examples` block in `config.yaml` is only documentation and is ignored by the script.

### Environment variables

| Variable     | Required | Description                          |
|--------------|----------|--------------------------------------|
| `NTFY_TOPIC` | yes      | Your ntfy topic. Keep it secret.     |

## Setup

### 1. Get notifications on your phone

Install the ntfy app and subscribe to a topic name that is hard to guess. Anyone who knows the topic can read or send notifications to it.

### 2. Run it locally

```bash
pip install -r requirements.txt
```

PowerShell:

```powershell
$env:NTFY_TOPIC="your-secret-topic"; python page-monitor.py
```

Bash:

```bash
NTFY_TOPIC=your-secret-topic python page-monitor.py
```

To test the notification end to end, add a temporary page to `config.yaml` that is guaranteed to match, for example `marker_present` with a word you know is on the page, or `marker_absent` with text that isn't. Remove it afterwards.

### 3. Run it automatically with GitHub Actions

The workflow lives in [`.github/workflows/simple-page-monitor.yml`](../.github/workflows/simple-page-monitor.yml) and runs every 6 hours (UTC). Store the topic as a repository secret, never in the code:

```bash
gh secret set NTFY_TOPIC
```

Trigger a manual run to test it:

```bash
gh workflow run simple-page-monitor.yml
gh run watch
```

Check what the script printed:

```bash
gh run view --log
```

A green run only means the script didn't crash. Look for one `is still unavailable` or `is available, notification sent` line per page in the log.

When you no longer need it, disable it so it stops notifying:

```bash
gh workflow disable simple-page-monitor.yml
```

## Notes

- **TLS:** the script mounts a `LegacyTLSAdapter` because some sites use older TLS settings that Python with OpenSSL 3 rejects by default (`SSLV3_ALERT_HANDSHAKE_FAILURE`). This lowers TLS strictness, which is fine for reading a public page, but don't reuse it for requests that send credentials.
- **Errors:** connection errors are printed as `Error fetching page: ...` and treated as "not ready yet".
- **Repeated alerts:** once a page meets its condition, you will be notified on every run until you disable the workflow or change the config.
- **JavaScript-rendered pages:** `requests` only sees the raw HTML. If the marker is injected by JavaScript, this approach won't detect it.
- **State file:** `changed` pages keep their last hash in `state.json`, which the workflow commits back to the repo. After the bot commits, run `git pull` before your next `git push`, or Git will reject the push because your local copy is behind.
