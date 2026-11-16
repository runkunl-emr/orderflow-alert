# orderflow-alert

**English** | [简体中文](README.zh-CN.md)

Read-only order-flow alerts for NQ / ES futures (and the micros MNQ / MES), built on the TradeStation 1-minute bar stream. It never places, changes or cancels orders — the login only asks for market-data access.

What it does:

- **Delta per bar** — `UpVolume − DownVolume`: volume traded on up-ticks minus down-ticks, a tick-rule estimate of aggressive buying minus aggressive selling. Every closed regular-session bar is printed as one JSON line.
- **Cumulative delta** since 09:30 New York time.
- **Single-print alert** — builds the day's market profile in 30-minute periods and sends a macOS notification when a single-print band appears: a band of price touched by only one period, at least 8% of the day's range, with prices touched by two or more periods both above and below it (a double-distribution day). A second notification fires when the band gets filled.
- **Live panel** at `http://127.0.0.1:8765` (this Mac only): candles, delta, cumulative delta, the 30-minute profile with the single-print band, and the alerts.

On 2025-02 … 2026-11 bars, a single-print band seen by 11:30 New York time was still standing at the close 42–44% of the time; one seen by 13:30, 70–72% of the time.

## Requirements

- macOS (notifications use `osascript`)
- Python 3.10+ — standard library only, no third-party packages
- A TradeStation account with an API key (client ID + secret). Every TradeStation API key comes with `http://localhost:3000` registered as a redirect URI, which the login uses.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/orderflow-login        # one time: asks for the API key and secret, then opens the TradeStation sign-in page
```

Credentials are stored in `~/Library/Application Support/orderflow-alert/tradestation.json` with mode `0600`.

## Usage

```bash
.venv/bin/orderflow-alert                      # watches @MNQ and @MES, opens the panel
.venv/bin/orderflow-alert --symbol @NQ --symbol @ES
```

| Option | Meaning |
|---|---|
| `--symbol SYMBOL` | NQ / ES / MNQ / MES symbol to watch; repeatable. Default `@MNQ` and `@MES`. |
| `--no-notify` | Only print JSON lines; no macOS notifications. |
| `--port N` | Panel port (default `8765`); `0` turns the panel off. |
| `--no-browser` | Serve the panel without opening it in the browser. |

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
