# orderflow-alert

**English** | [简体中文](README.zh-CN.md)

Read-only order-flow alerts for NQ / ES futures (and the micros MNQ / MES), with data from **TradeStation** or **Interactive Brokers**. It never places, changes or cancels orders: the TradeStation login only asks for market-data access, and the IBKR connection is opened read-only.

What it does:

- **Delta per bar** — volume traded on up-ticks minus volume traded on down-ticks, a tick-rule estimate of aggressive buying minus aggressive selling. Every closed regular-session bar is printed as one JSON line.
- **Cumulative delta** since 09:30 New York time.
- **Single-print alert** — builds the day's market profile in 30-minute periods and sends a macOS notification when a single-print band appears: a band of price touched by only one period, at least 8% of the day's range, with prices touched by two or more periods both above and below it (a double-distribution day). A second notification fires when the band gets filled.
- **Live panel** at `http://127.0.0.1:8765` (this Mac only): candles, delta, cumulative delta, the 30-minute profile with the single-print band, and the alerts.

On 2025-02 … 2026-11 bars, a single-print band seen by 11:30 New York time was still standing at the close 42–44% of the time; one seen by 13:30, 70–72% of the time.

## Data sources

| | TradeStation (default) | Interactive Brokers |
|---|---|---|
| Delta from | the bar stream's own up-tick / down-tick volume | tick-by-tick trades, classified with the tick rule |
| Today's bars before start | backfilled with delta | backfilled **without** delta (IBKR history has no buy/sell split): the profile is complete, cumulative delta counts from when the program started |
| Extra package | none — standard library only | `ib_async` |
| Runs against | TradeStation's web API | a running TWS or IB Gateway |

Both use the same tick rule, so their deltas are comparable. Adding another broker means writing one source that yields `bars.Bar` objects; `flow_alert` never sees broker fields.

## Requirements

- macOS (notifications use `osascript`)
- Python 3.10+
- **TradeStation:** an account with an API key (client ID + secret). Every TradeStation API key comes with `http://localhost:3000` registered as a redirect URI, which the login uses.
- **IBKR:** TWS or IB Gateway running with the API enabled (in its API settings, turn on *Enable ActiveX and Socket Clients*), and real-time CME futures market data on the account.

## Setup

TradeStation:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/orderflow-login        # one time: asks for the API key and secret, then opens the TradeStation sign-in page
```

Credentials are stored in `~/Library/Application Support/orderflow-alert/tradestation.json` with mode `0600`.

IBKR:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[ibkr]'
```

## Usage

```bash
.venv/bin/orderflow-alert                      # TradeStation; watches @MNQ and @MES, opens the panel
.venv/bin/orderflow-alert --symbol @NQ --symbol @ES
.venv/bin/orderflow-alert --source ibkr        # IBKR via TWS on 127.0.0.1:7496
.venv/bin/orderflow-alert --source ibkr --ib-port 4002   # IB Gateway, paper account
```

| Option | Meaning |
|---|---|
| `--symbol SYMBOL` | NQ / ES / MNQ / MES symbol to watch; repeatable. Default `@MNQ` and `@MES`. |
| `--no-notify` | Only print JSON lines; no macOS notifications. |
| `--port N` | Panel port (default `8765`); `0` turns the panel off. |
| `--no-browser` | Serve the panel without opening it in the browser. |
| `--source` | `tradestation` (default) or `ibkr`. |
| `--ib-host` / `--ib-port` | Where TWS / IB Gateway listens. Default `127.0.0.1:7496` (TWS live). TWS paper `7497`, Gateway live `4001`, Gateway paper `4002`. |
| `--ib-client-id` | API client ID, unique among programs connected to the same TWS (default `17`). |

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q             # no TWS or TradeStation login needed
```

## License

MIT — see [LICENSE](LICENSE).
