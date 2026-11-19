"""Money Flow Index alerts: notify when MFI(14) on 5-minute bars moves into or out of the 20 / 80 zones.

MFI is computed on continuous bars (pre-market included), so it has a value from the first bar of the session and
matches the MFI that charting platforms plot. Alerts fire only for bars that close in the regular session.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from .bars import Bar

ET = ZoneInfo("America/New_York")
LENGTH = 14
OVERSOLD = 20.0
OVERBOUGHT = 80.0
KEEP = LENGTH + 50   # completed bars kept in memory


def money_flow(bars: list[Bar], length: int = LENGTH) -> list[float | None]:
    """Classic MFI as plotted by TradeStation TITAN X (and TradingView ta.mfi(hlc3)).

    Typical price = (H+L+C)/3, flow = typical * Volume; flow is positive when typical rises, negative when it
    falls, ignored when unchanged. MFI = 100 * positive / (positive + negative) over `length` bars.
    """
    typical = [(b.high + b.low + b.close) / 3 for b in bars]
    flow = [t * b.volume for t, b in zip(typical, bars)]
    positive = [0.0] + [flow[i] if typical[i] > typical[i - 1] else 0.0 for i in range(1, len(bars))]
    negative = [0.0] + [flow[i] if typical[i] < typical[i - 1] else 0.0 for i in range(1, len(bars))]
    out: list[float | None] = []
    for i in range(len(bars)):
        if i < length:  # needs `length` bars that each have a previous bar
            out.append(None)
            continue
        up = sum(positive[i - length + 1:i + 1])
        total = up + sum(negative[i - length + 1:i + 1])
        out.append(100 * up / total if total else None)
    return out


def crossing(prev: float | None, cur: float | None) -> str | None:
    """How MFI moved between two bars relative to the 20 / 80 lines, or None."""
    if prev is None or cur is None:
        return None
    if prev >= OVERSOLD > cur:
        return f"跌破 {OVERSOLD:g}"
    if prev < OVERSOLD <= cur:
        return f"回升穿过 {OVERSOLD:g}"
    if prev <= OVERBOUGHT < cur:
        return f"涨破 {OVERBOUGHT:g}"
    if prev > OVERBOUGHT >= cur:
        return f"回落穿过 {OVERBOUGHT:g}"
    return None


def in_session(end: dt.datetime) -> bool:
    """True when a bar closes inside 09:30-16:00 ET on a weekday."""
    e = end.astimezone(ET)
    m = e.hour * 60 + e.minute
    return e.weekday() < 5 and 570 < m <= 960


class MfiWatcher:
    """Builds N-minute bars from closed 1-minute bars, tracks MFI, and alerts on 20 / 80 crossings."""

    def __init__(self, symbol: str, notify, log=None, minutes: int = 5, length: int = LENGTH):
        self.symbol, self.notify, self.minutes, self.length = symbol, notify, minutes, length
        self.log = log or (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
        self.last_end: dt.datetime | None = None   # last 1-minute bar taken in (reconnect backfill repeats bars)
        self.cur: dict | None = None               # the N-minute bar being built
        self.bars: list[Bar] = []                  # completed N-minute bars
        self.prev: float | None = None             # MFI of the previous completed bar

    def _bucket_end(self, end: dt.datetime) -> dt.datetime:
        start = (end - dt.timedelta(minutes=1)).astimezone(ET)
        floor = start.replace(minute=start.minute - start.minute % self.minutes, second=0, microsecond=0)
        return floor + dt.timedelta(minutes=self.minutes)

    def on_bar(self, bar: Bar) -> None:
        if not bar.closed or (self.last_end is not None and bar.end <= self.last_end):
            return
        self.last_end = bar.end
        end = self._bucket_end(bar.end)
        if self.cur and self.cur["end"] != end:   # a minute was missing: close the previous bucket as it is
            self._complete()
        if not self.cur:
            self.cur = {"end": end, "open": bar.open, "high": bar.high, "low": bar.low, "volume": 0.0}
        c = self.cur
        c["high"], c["low"], c["close"] = max(c["high"], bar.high), min(c["low"], bar.low), bar.close
        c["volume"] += bar.volume
        c["realtime"] = bar.realtime
        if bar.end.astimezone(ET) >= end:   # the bucket's last minute has closed
            self._complete()

    def _complete(self) -> None:
        c, self.cur = self.cur, None
        bar = Bar(end=c["end"], open=c["open"], high=c["high"], low=c["low"], close=c["close"],
                  buy_volume=0, sell_volume=0, closed=True, realtime=c["realtime"], volume=c["volume"])
        self.bars = (self.bars + [bar])[-KEEP:]
        mfi = money_flow(self.bars, self.length)[-1]
        hhmm = bar.end.astimezone(ET).strftime("%H:%M")
        self.log({"event": "mfi", "symbol": self.symbol, "minutes": self.minutes, "time": hhmm,
                  "mfi": None if mfi is None else round(mfi, 1)})
        move = crossing(self.prev, mfi)
        if move and bar.realtime and in_session(bar.end):
            self.notify(f"{self.symbol.lstrip('@')} {self.minutes}分钟 MFI {move}（{mfi:.1f}）· {hhmm}")
        self.prev = mfi
