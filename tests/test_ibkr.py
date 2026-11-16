import datetime as dt
import types

import pytest

from orderflow_alert.flow_alert import FlowWatcher
from orderflow_alert.ibkr import IBKRSource, TickBars

UTC = dt.timezone.utc


def at(hh, mm, ss=0):
    return dt.datetime(2026, 11, 12, hh, mm, ss, tzinfo=UTC)


def test_tick_rule_buy_sell_and_zero_ticks():
    b = TickBars()
    b.trade(at(15, 0, 1), 100.00, 3)          # first trade: no previous price, side unknown, not counted
    b.trade(at(15, 0, 2), 100.25, 2)          # up-tick: buy
    b.trade(at(15, 0, 3), 100.25, 4)          # zero-tick: keeps the previous side (buy)
    b.trade(at(15, 0, 4), 100.00, 5)          # down-tick: sell
    bar = b.trade(at(15, 0, 5), 100.00, 1)[-1]  # zero-tick after a sell: sell
    assert (bar.buy_volume, bar.sell_volume, bar.delta) == (6, 6, 0)
    assert (bar.open, bar.high, bar.low, bar.close, bar.closed) == (100.0, 100.25, 100.0, 100.0, False)


def test_new_minute_closes_previous_bar():
    b = TickBars()
    b.trade(at(15, 0, 10), 50.0, 1)
    b.trade(at(15, 0, 20), 51.0, 2)
    out = b.trade(at(15, 1, 5), 52.0, 7)      # first trade of 15:01
    closed, forming = out
    assert closed.closed and closed.end == at(15, 1) and (closed.open, closed.close, closed.delta) == (50.0, 51.0, 2)
    assert not forming.closed and forming.end == at(15, 2) and forming.open == 52.0 and forming.buy_volume == 7


def test_flush_closes_bar_without_another_trade():
    b = TickBars()
    b.trade(at(15, 0, 10), 50.0, 1)
    assert b.flush(at(15, 0, 59)) is None
    bar = b.flush(at(15, 1, 0))
    assert bar.closed and bar.end == at(15, 1)
    assert b.flush(at(15, 1, 30)) is None     # nothing forming any more


def test_ibkr_bars_drive_the_watcher():
    """Trades in 09:31, 09:32, 09:33 ET become bars that reach FlowWatcher with their tick-rule delta."""
    logs = []
    w = FlowWatcher("@MES", lambda text: None, logs.append)
    b = TickBars()
    for minute, prices in enumerate([[7600, 7601, 7602], [7602, 7601, 7600], [7600, 7600.25]]):
        for i, p in enumerate(prices):
            for bar in b.trade(at(14, 31 + minute, i * 10), p, 1):   # 14:31 UTC = 09:31 ET
                w.on_bar(bar)
    w.on_bar(b.flush(at(14, 34)))
    bars = [e for e in logs if e["event"] == "bar"]
    assert [e["time"] for e in bars] == ["09:32", "09:33", "09:34"]   # labelled by close time, like TradeStation
    # first trade unclassified; a minute's opening trade at the previous price keeps the previous side
    assert [e["delta"] for e in bars] == [2, -1, 0]
    assert bars[-1]["cum_delta"] == 1


class FakeSource(IBKRSource):
    """IBKRSource with the TWS connection replaced: _open returns canned history and queues canned events."""

    def __init__(self, history, events):
        self.history, self.events, self.closed = history, events, False
        self._connect_lock = __import__("threading").Lock()

    def _call(self, coro, timeout=60):
        import asyncio
        return asyncio.run(coro)

    async def _open(self, symbol, since, out):
        for e in self.events:
            out.put(e)
        return "front", "ticker", {}, self.history

    async def _close(self, front, ticker, handlers):
        self.closed = True


def hist(start):
    return types.SimpleNamespace(date=start, open=1.0, high=2.0, low=0.5, close=1.5)


def test_stream_backfills_then_goes_live_and_raises_on_error():
    now = dt.datetime.now(UTC).replace(second=0, microsecond=0)
    history = [hist(now - dt.timedelta(minutes=3)), hist(now - dt.timedelta(minutes=2)), hist(now)]   # last one still open
    t0 = now + dt.timedelta(seconds=1)
    events = [("trade", t0, 10.0, 1), ("trade", t0, 10.25, 2), ("error", "IBKR error 10089: no market data")]
    src = FakeSource(history, events)
    got = []
    with pytest.raises(RuntimeError, match="10089"):
        for bar in src.stream("@MES", now - dt.timedelta(hours=1)):
            got.append(bar)
    backfill = [b for b in got if not b.realtime]
    assert len(backfill) == 2                                          # the still-open history bar is skipped
    assert all(b.closed and b.delta == 0 for b in backfill)            # history has no buy/sell split
    assert got[-1].realtime and not got[-1].closed and got[-1].close in (10.0, 10.25)
    assert src.closed                                                  # subscription cleaned up on the way out
