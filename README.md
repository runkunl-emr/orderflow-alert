# orderflow-alert

**English** | [简体中文](README.zh-CN.md)

## 1. Purpose

This tool monitors [order flow](https://en.wikipedia.org/wiki/Order_flow_trading) on [NQ](https://en.wikipedia.org/wiki/E-mini) and [ES](https://en.wikipedia.org/wiki/E-mini_S%26P) [futures](https://en.wikipedia.org/wiki/Futures_contract). It also monitors the [micro contracts](https://en.wikipedia.org/wiki/E-mini) MNQ and MES.

It gets data from [TradeStation](https://en.wikipedia.org/wiki/TradeStation) or from [Interactive Brokers](https://en.wikipedia.org/wiki/Interactive_Brokers) (IBKR).

It does not place, change or cancel orders.

## 2. What the tool shows

| Item | Meaning |
|---|---|
| Delta | Buy [volume](https://en.wikipedia.org/wiki/Volume_%28finance%29) minus sell volume in one 1-minute bar. |
| Cumulative delta | The sum of all deltas since 09:30 New York time. |
| Single-print band (*single prints*) | A price area that only one 30-minute period touched. Other periods traded above it and below it. This shape is a *double distribution*. |
| Band filled | Price came back into the band. The band is gone. |

The tool builds a [Market Profile](https://en.wikipedia.org/wiki/Market_profile) of the day in 30-minute periods. It finds the single-print bands in this profile.

The tool counts a trade at a higher price than the previous trade as a buy. It counts a trade at a lower price as a sell. A trade at the same price gets the side of the previous trade. This method is the *tick rule*.

The tool sends a macOS notification when a band starts. It sends one more notification when the band is filled.

NOTE: Wikipedia has no article on single prints, double distribution or the tick rule. For the background, refer to the Market Profile article.

NOTE: From February 2025 to November 2026, 42–44% of bands found by 11:30 New York time were still open at the close. For bands found by 13:30, the value was 70–72%.

## 3. Before you start

Make sure that you have these items:

- [ ] A Mac.
- [ ] Python 3.10 or later.
- [ ] One of these broker accounts:
  - [ ] TradeStation, with an API key (client ID and client secret).
  - [ ] IBKR, with real-time [CME](https://en.wikipedia.org/wiki/CME_Group) futures market data, and TWS or IB Gateway installed.

## 4. Install

### 4.1 TradeStation

1. Open Terminal.
2. Go to the project folder.
3. Type `python3 -m venv .venv` and push Return.
4. Type `.venv/bin/pip install -e .` and push Return.
5. Type `.venv/bin/orderflow-login` and push Return.
6. Type your API key and push Return.
7. Type your API secret and push Return.

   Result: The TradeStation sign-in page opens in your browser.

8. Sign in to TradeStation.
9. Accept the access request.

   Result: The page shows "TradeStation login received".

NOTE: The tool asks only for market data access. It cannot see or change your account.

NOTE: The tool keeps your credentials in `~/Library/Application Support/orderflow-alert/tradestation.json`. Only your user can read this file.

### 4.2 IBKR

1. Open Terminal.
2. Go to the project folder.
3. Type `python3 -m venv .venv` and push Return.
4. Type `.venv/bin/pip install -e '.[ibkr]'` and push Return.
5. Start TWS or IB Gateway.
6. Open its API settings.
7. Turn on **Enable ActiveX and Socket Clients**.
8. Turn on **Read-Only API**.

NOTE: The tool does not contain code that sends orders. Step 8 is an additional protection: with **Read-Only API** on, TWS refuses orders from all API programs.

## 5. Start the tool

1. If you use IBKR, make sure that TWS or IB Gateway is running.
2. In Terminal, go to the project folder.
3. Type `.venv/bin/orderflow-alert` and push Return.

   Result: The first line shows the broker in use. Example: `flow alert started: ibkr (auto: no TradeStation login, ib_async installed)`.

   Result: The panel opens in your browser at `http://127.0.0.1:8765`.

The tool selects the broker automatically:

| Condition | Broker in use |
|---|---|
| You did the TradeStation login (step 4.1). | TradeStation |
| You did not do the TradeStation login, and you installed the IBKR package (step 4.2). | IBKR |
| You did neither. | None. The tool shows how to set up a broker and stops. |

To use IBKR when you also have a TradeStation login, add `--source ibkr`.

To stop the tool, push Control-C.

## 6. Options

| Option | Function | Default |
|---|---|---|
| `--symbol SYMBOL` | Selects a contract to monitor. Use it one time for each contract. | `@MNQ` and `@MES` |
| `--source NAME` | Selects the broker: `auto`, `tradestation` or `ibkr`. | `auto` |
| `--port N` | Sets the panel port. `0` turns the panel off. | `8765` |
| `--no-browser` | Starts the panel but does not open the browser. | Off |
| `--no-notify` | Stops macOS notifications. The tool only writes lines in Terminal. | Off |
| `--ib-host HOST` | Sets the address of TWS or IB Gateway. | `127.0.0.1` |
| `--ib-port N` | Sets the port of TWS or IB Gateway. | `7496` |
| `--ib-client-id N` | Sets the API client ID. Use a number that no other program uses on the same TWS. | `17` |

IBKR ports:

| Program | Live account | Paper account |
|---|---|---|
| TWS | 7496 | 7497 |
| IB Gateway | 4001 | 4002 |

Examples:

- Monitor NQ and ES: `.venv/bin/orderflow-alert --symbol @NQ --symbol @ES`
- Use IB Gateway with a paper account: `.venv/bin/orderflow-alert --ib-port 4002`

## 7. Troubleshooting

| Problem | Cause | Action |
|---|---|---|
| `tradestation.json is missing` | You did not do the TradeStation login. | Do step 4.1. |
| `No data source set up` | No broker is set up. | Do step 4.1 or step 4.2. |
| `Connect call failed ... 7496` | TWS or IB Gateway is not running, its API is off, or the port is wrong. | Start TWS or IB Gateway. Turn on the API (step 4.2). Check the port (section 6). |
| `IBKR error 354` or `IBKR error 10089` | The IBKR account does not have real-time CME market data. | Subscribe to CME futures market data in IBKR Client Portal. |
| The panel does not open. Port 8765 is in use. | Another program uses port 8765. | Start with a different port, for example `--port 8766`. |
| No notifications. | The market is closed, or the bars are history. | Wait for the regular session: Monday to Friday, 09:30–16:00 New York time. |

NOTE: The tool does not send notifications for bars that it gets as history when it starts. It uses these bars only to build the profile.

NOTE: When the connection stops, the tool tries again every 5 seconds. You do not have to restart it.

## 8. Limits

- IBKR history bars have no buy and sell volume. Thus, with IBKR, cumulative delta starts when the tool starts. To get the full value, start the tool before 09:30 New York time.
- The tool estimates buy and sell volume from price changes. It does not use the exchange's own buyer and seller data.
- The tool runs on macOS only, because the notifications use macOS.

## 9. Add a different broker

The main code uses only the `Bar` type in `orderflow_alert/bars.py`.

To add a broker:

1. Write a source class that yields `Bar` objects.
2. Add the class to `make_source` in `orderflow_alert/flow_alert.py`.

Use `orderflow_alert/tradestation.py` and `orderflow_alert/ibkr.py` as examples.

## 10. Tests

1. Type `.venv/bin/pip install -e '.[dev]'` and push Return.
2. Type `.venv/bin/pytest -q` and push Return.

   Result: All tests pass.

NOTE: The tests do not need TWS or a TradeStation login.

## 11. License

MIT. Refer to [LICENSE](LICENSE).
