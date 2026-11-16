"""The broker-neutral 1-minute bar that flow_alert works on, and the interface a data source implements.

Adding a broker means writing one source that yields these bars; flow_alert itself never sees broker fields.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class Bar:
    end: dt.datetime   # the bar's close time, timezone-aware
    open: float
    high: float
    low: float
    close: float
    buy_volume: int    # estimated aggressive buying: volume traded on up-ticks (tick rule)
    sell_volume: int   # estimated aggressive selling: volume traded on down-ticks
    closed: bool       # False while the bar is still forming
    realtime: bool     # False for backfilled history: it rebuilds the state but never alerts

    @property
    def delta(self) -> int:
        return self.buy_volume - self.sell_volume


class BarSource(Protocol):
    name: str

    def stream(self, symbol: str, since: dt.datetime) -> Iterator[Bar]:
        """Backfill bars from `since` (realtime=False), then yield live bars: the forming bar again on updates,
        and each bar once more with closed=True. Return or raise when the connection drops; the caller reconnects."""
        ...
