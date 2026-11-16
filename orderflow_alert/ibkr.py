"""Interactive Brokers source: trades from TWS / IB Gateway, aggregated into 1-minute bars with tick-rule buy/sell volume.

IBKR's bars carry total volume only, so delta is built from tick-by-tick trades ("Last"): a trade above the previous
price counts as buying, below as selling, at the same price it keeps the previous trade's side (the tick rule; the
same idea as TradeStation's UpVolume / DownVolume, so deltas from the two sources are comparable).

Today's bars before the program started are backfilled from IBKR's 1-minute history. Those have no buy/sell split,
so they rebuild the market profile but count as zero delta: cumulative delta covers only the time the program has
been running.

Needs: `pip install 'orderflow-alert[ibkr]'`, TWS or IB Gateway running with the API enabled, and real-time CME
market data on the account. This module never sends orders. To make TWS itself refuse orders from any API
client, turn on "Read-Only API" in the TWS / IB Gateway API settings.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import queue
import threading
import time
from typing import Iterator

from .bars import Bar

FORMING_EVERY = 0.25   # seconds between updates of the still-forming bar sent to the panel
EXCHANGE = "CME"       # NQ, ES, MNQ, MES all trade on CME Globex


class TickBars:
    """Turns a stream of trades into 1-minute bars with tick-rule buy/sell volume. Pure; no I/O."""

    def __init__(self):
        self.last_price: float | None = None
        self.last_side = 0          # +1 buy, -1 sell, 0 unknown (only before the first price change)
        self.start: dt.datetime | None = None
        self.o = self.h = self.l = self.c = 0.0
        self.buy = self.sell = 0

    def _bar(self, closed: bool) -> Bar:
        return Bar(end=self.start + dt.timedelta(minutes=1), open=self.o, high=self.h, low=self.l, close=self.c,
                   buy_volume=self.buy, sell_volume=self.sell, closed=closed, realtime=True)

    def trade(self, when: dt.datetime, price: float, size: float) -> list[Bar]:
        """Add one trade. Returns the bar it closed (if this trade starts a new minute) and the forming bar."""
        out: list[Bar] = []
        minute = when.astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
        if self.start is not None and minute > self.start:
            out.append(self._bar(closed=True))
            self.start = None
        if self.last_price is not None and price != self.last_price:
            self.last_side = 1 if price > self.last_price else -1
        self.last_price = price
        if self.start is None:
            self.start, self.o, self.h, self.l, self.buy, self.sell = minute, price, price, price, 0, 0
        self.h, self.l, self.c = max(self.h, price), min(self.l, price), price
        if self.last_side > 0:
            self.buy += int(size)
        elif self.last_side < 0:
            self.sell += int(size)
        out.append(self._bar(closed=False))
        return out

    def flush(self, now: dt.datetime) -> Bar | None:
        """Close the forming bar once its minute is over, even if no further trade has arrived."""
        if self.start is not None and now >= self.start + dt.timedelta(minutes=1):
            bar = self._bar(closed=True)
            self.start = None
            return bar
        return None


class IBKRSource:
    """Bars from IBKR. One API connection, run on its own asyncio thread, shared by all symbols."""

    name = "ibkr"

    def __init__(self, host: str = "127.0.0.1", port: int = 7496, client_id: int = 17):
        try:
            import ib_async  # noqa: F401
        except ImportError:
            raise SystemExit("The IBKR source needs ib_async: pip install 'orderflow-alert[ibkr]'") from None
        self.host, self.port, self.client_id = host, port, client_id
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="ibkr").start()
        self.ib = None
        self._connect_lock = threading.Lock()

    def _call(self, coro, timeout: float = 60):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _connect(self):
        from ib_async import IB
        from ib_async.ib import StartupFetch
        if self.ib is None:
            self.ib = IB()
        if not self.ib.isConnected():
            # readonly=True tells ib_async that TWS may be in Read-Only API mode (it does not block orders by itself;
            # the TWS setting does). This module sends no orders either way. Fetch nothing account-related at startup.
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id, readonly=True,
                                       fetchFields=StartupFetch(0))
        return self.ib

    async def _open(self, symbol: str, since: dt.datetime, out: queue.Queue):
        """Resolve the front-month contract, fetch today's history, and start the trade feed into `out`."""
        from ib_async import ContFuture, Future
        ib = await self._connect()
        root = symbol.lstrip("@").upper()
        cont = (await ib.qualifyContractsAsync(ContFuture(root, EXCHANGE)))[0]
        if cont is None:
            raise RuntimeError(f"IBKR does not know the {root} future on {EXCHANGE}")
        front = (await ib.qualifyContractsAsync(Future(conId=cont.conId, exchange=EXCHANGE)))[0]

        history = []
        seconds = int((dt.datetime.now(dt.timezone.utc) - since).total_seconds())
        if seconds > 60:
            history = await ib.reqHistoricalDataAsync(front, endDateTime="", durationStr=f"{min(seconds + 60, 86400)} S",
                                                      barSizeSetting="1 min", whatToShow="TRADES", useRTH=True, formatDate=2)

        def on_update(ticker):
            for t in ticker.tickByTicks:
                out.put(("trade", t.time, float(t.price), float(t.size)))

        def on_error(req_id, code, text, contract=None):
            if contract is not None and getattr(contract, "conId", None) == front.conId and code not in (2104, 2106, 2158):
                out.put(("error", f"IBKR error {code}: {text}"))

        def on_disconnect():
            out.put(("error", "disconnected from TWS / IB Gateway"))

        ticker = ib.reqTickByTickData(front, "Last")
        handlers = {"update": on_update, "error": on_error, "disconnect": on_disconnect}
        ticker.updateEvent += on_update
        ib.errorEvent += on_error
        ib.disconnectedEvent += on_disconnect
        return front, ticker, handlers, list(history)

    async def _close(self, front, ticker, handlers):
        """Cancel the feed and unhook this stream's handlers, so reconnects don't pile them up."""
        ticker.updateEvent -= handlers["update"]
        self.ib.errorEvent -= handlers["error"]
        self.ib.disconnectedEvent -= handlers["disconnect"]
        if self.ib.isConnected():
            self.ib.cancelTickByTickData(front, "Last")

    def stream(self, symbol: str, since: dt.datetime) -> Iterator[Bar]:
        out: queue.Queue = queue.Queue()
        with self._connect_lock:
            front, ticker, handlers, history = self._call(self._open(symbol, since, out))
        try:
            now = dt.datetime.now(dt.timezone.utc)
            for b in history:   # formatDate=2: b.date is the bar's start, in UTC
                start = b.date if isinstance(b.date, dt.datetime) else dt.datetime.combine(b.date, dt.time(), dt.timezone.utc)
                end = start + dt.timedelta(minutes=1)
                if end <= now:   # skip the still-open last bar; the trade feed rebuilds it
                    yield Bar(end=end, open=b.open, high=b.high, low=b.low, close=b.close,
                              buy_volume=0, sell_volume=0, closed=True, realtime=False)
            bars, sent = TickBars(), 0.0
            while True:
                try:
                    item = out.get(timeout=1)
                except queue.Empty:
                    closed = bars.flush(dt.datetime.now(dt.timezone.utc))
                    if closed:
                        yield closed
                    continue
                if item[0] == "error":
                    raise RuntimeError(item[1])
                _, when, price, size = item
                for bar in bars.trade(when, price, size):
                    if bar.closed or time.monotonic() - sent >= FORMING_EVERY:
                        sent = time.monotonic() if not bar.closed else sent
                        yield bar
        finally:
            try:
                self._call(self._close(front, ticker, handlers), timeout=10)
            except Exception:
                pass
