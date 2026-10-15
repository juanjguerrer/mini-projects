# football-alerts

A small Go program that sends a push notification (via [ntfy.sh](https://ntfy.sh)) when Real Madrid's next match is less than 24 hours away. It started as a proof of concept to learn Go; there are plenty of football apps, but building this one was the point.

> This README was written with the help of [Claude](https://claude.ai) (Anthropic).

## How it works

1. Loads `.env` (if present) and fetches the team's matches from the [football-data.org](https://www.football-data.org) API (`GET /v4/teams/86/matches`).
2. Picks the next match that has not been played yet, skipping `POSTPONED` and `CANCELLED` ones.
3. If that match starts within the next 24 hours and no alert was sent for it, sends a notification with the teams, the competition and the kickoff time in Mexico City time.
4. Records the alert in `sent_alerts.json`, so running the program again does not notify twice. The alert is recorded only if ntfy accepted it.

It does one check per execution and exits. It is meant to be run on a schedule.

## Setup

### 1. Get an API key

Create a free account at [football-data.org](https://www.football-data.org) and copy your token. The free tier includes La Liga and the Champions League, allows 10 requests per minute, and scores are delayed.

### 2. Get notifications on your phone

Install the ntfy app and subscribe to a topic name that is hard to guess. Anyone who knows the topic can read it or send notifications to it.

### 3. Configure environment variables

Create a `.env` file in this folder (it is ignored by Git):

```
FOOTBALL_DATA_API_KEY=your_token
NTFY_TOPIC_FOOTBALL=your-secret-topic
```

| Variable                | Required | Description                      |
|-------------------------|----------|----------------------------------|
| `FOOTBALL_DATA_API_KEY` | yes      | Your football-data.org token.    |
| `NTFY_TOPIC_FOOTBALL`   | yes      | Your ntfy topic. Keep it secret. |

### 4. Run it

```
go run .
```

Or build it once and run the binary, which starts faster than `go run`:

```
go build -o football-alerts .
./football-alerts
```

## Notes

- The team is hard-coded: Real Madrid has id `86` in football-data.org.
- Times are converted to `America/Mexico_City`. The program embeds the time zone database, so it also works on Windows.
- `sent_alerts.json` maps alert keys such as `next_575325` to `true`. Delete the file to receive the alert again.
- The program stops with an error if the API key or the topic is missing, or if the API or ntfy answer with an error.

## Status and next steps

Only the "next match in 24 hours" alert exists so far. Planned:

- more alert moments (for example 1 hour before) and the final score
- tests for the decision logic
- a GitHub Actions schedule, committing `sent_alerts.json` back like `simple-page-monitor` does with `state.json`
