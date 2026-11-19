"""Read-only order-flow alerts on NQ/ES futures from a broker's 1-minute bars (never places orders).

Data comes from a pluggable source (bars.BarSource): TradeStation's bar stream, or IBKR trades aggregated into bars.
Every closed RTH bar is printed as one JSON line with its delta (buy volume - sell volume: volume on up-ticks minus
down-ticks, a tick-rule estimate of aggressive buying minus selling) and the cumulative delta since 09:30 ET.
A macOS notification fires when the day's market profile shows a single-print band, i.e. a double-distribution
shape: 30-minute periods, a band of price touched by only one period that is at least 8% of the day's range,
with prices touched by two or more periods both above and below it. A second one fires when that band is filled.
On 2025-02..2026-11 bars such a band seen by 11:30 still stood at the close 42-44% of the time, by 13:30 70-72%.

A local panel at http://127.0.0.1:8765 (this Mac only) charts the same data live: candles, delta, cumulative
delta, the 30-minute profile with the single-print band, and the alerts.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import http.server
import json
import queue
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from zoneinfo import ZoneInfo

from .bars import Bar, BarSource
from .mfi import MfiWatcher

ET = ZoneInfo("America/New_York")
BIN = {"NQ": 5.0, "ES": 1.25}  # price bucket for the profile, in points
MIN_BAND = 0.08  # single-print band height as a fraction of the day's range
PANEL_HTML = Path(__file__).with_name("flow_panel.html")


class Hub:
    """Today's RTH bars, single-print bands and alerts, fanned out to the panel's browser connections."""

    def __init__(self):
        self.lock = threading.Lock()
        self.metas: dict[str, dict] = {}
        self.bars: dict[str, dict[int, dict]] = collections.defaultdict(dict)  # symbol -> chart time -> bar event
        self.bands: dict[str, dict] = {}
        self.days: dict[str, dt.date] = {}
        self.alerts: collections.deque = collections.deque(maxlen=50)
        self.clients: list[queue.Queue] = []

    def _send(self, event: dict) -> None:
        for q in self.clients:
            try:
                q.put_nowait(event)
            except queue.Full:  # a stalled browser tab misses updates rather than growing memory
                pass

    def meta(self, symbol: str, size: float) -> None:
        with self.lock:
            self.metas[symbol] = {"type": "meta", "symbol": symbol, "bin": size}
            self._send(self.metas[symbol])

    def bar(self, symbol: str, bar: Bar, minute: int) -> None:
        day = bar.end.astimezone(ET).date()
        # chart time: the bar's start as ET wall-clock seconds, since the chart library draws times in UTC
        t = int((bar.end - dt.timedelta(minutes=1)).astimezone(ET).replace(tzinfo=dt.timezone.utc).timestamp())
        event = {"type": "bar", "symbol": symbol, "time": t, "minute": minute, "open": bar.open,
                 "high": bar.high, "low": bar.low, "close": bar.close, "delta": bar.delta}
        with self.lock:
            if self.days.get(symbol) != day:
                self.days[symbol] = day
                self.bars[symbol] = {}
                self.bands.pop(symbol, None)
                self._send({"type": "reset", "symbol": symbol})
            self.bars[symbol][t] = event
            self._send(event)

    def band(self, symbol: str, band: tuple[float, float] | None) -> None:
        event = {"type": "band", "symbol": symbol, "band": {"low": band[0], "high": band[1]} if band else None}
        with self.lock:
            self.bands[symbol] = event
            self._send(event)

    def alert(self, text: str) -> None:
        event = {"type": "alert", "time": dt.datetime.now(ET).strftime("%H:%M:%S"), "text": text}
        with self.lock:
            self.alerts.append(event)
            self._send(event)

    def subscribe(self) -> tuple[queue.Queue, list[dict]]:
        """A queue of future events plus the current state to replay first."""
        q: queue.Queue = queue.Queue(maxsize=5000)
        with self.lock:
            snapshot = list(self.metas.values())
            for symbol, bars in self.bars.items():
                snapshot += [bars[t] for t in sorted(bars)]
            snapshot += list(self.bands.values()) + list(self.alerts)
            self.clients.append(q)
        return q, snapshot

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients.remove(q)


def serve_panel(hub: Hub, port: int) -> http.server.ThreadingHTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                body = PANEL_HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":  # server-sent events, one JSON object each
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q, snapshot = hub.subscribe()
                try:
                    for event in snapshot:
                        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
                    while True:
                        try:
                            self.wfile.write(f"data: {json.dumps(q.get(timeout=15))}\n\n".encode())
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    hub.unsubscribe(q)
            else:
                self.send_error(404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def bucket(symbol: str) -> float:
    root = symbol.lstrip("@").upper()[:3]
    return BIN[root[1:] if root.startswith("M") else root[:2]]


def rth_minute(end: dt.datetime) -> int | None:
    """Minutes since 09:30 ET at the bar's open, or None outside 09:30-16:00 on a weekday."""
    e = end.astimezone(ET)
    m = e.hour * 60 + e.minute - 1 - 570
    return m if e.weekday() < 5 and 0 <= m < 390 else None


def price(x: float) -> str:
    """A price as written on the chart: 27353.75, 7345, 7389.5. (`:g` keeps only 6 significant digits.)"""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def single_print_band(bars: list[tuple[int, float, float]], size: float) -> tuple[float, float] | None:
    """Tallest single-print band inside the profile of (minute, high, low) bars, as (low, high) prices."""
    if not bars:
        return None
    lo = min(b[2] for b in bars)
    hi = max(b[1] for b in bars)
    n = int((hi - lo) / size) + 1
    periods: dict[int, list] = collections.defaultdict(list)
    for m, h, l in bars:
        periods[m // 30].append((h, l))
    count = [0] * n
    for p in periods.values():
        for k in range(int((min(l for _, l in p) - lo) / size), int((max(h for h, _ in p) - lo) / size) + 1):
            count[k] += 1
    best, run = None, 0
    for k in range(n):
        run = run + 1 if count[k] == 1 else 0
        if run and max(count[:k - run + 1] or [0]) >= 2 and max(count[k + 1:] or [0]) >= 2 and (best is None or run > best[1] - best[0]):
            best = (k - run + 1, k + 1)
    if best is None or (best[1] - best[0]) * size < MIN_BAND * (hi - lo):
        return None
    return lo + best[0] * size, lo + best[1] * size


class FlowWatcher:
    def __init__(self, symbol: str, notify, log=None, hub: Hub | None = None):
        self.symbol = symbol
        self.size = bucket(symbol)
        self.notify = notify
        self.log = log or (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
        self.hub = hub
        self.day: dt.date | None = None
        self.bars: dict[int, tuple[float, float, int]] = {}  # minute -> (high, low, delta), closed RTH bars only
        self.band: tuple[float, float] | None = None
        self.alerted: tuple[float, float] | None = None   # the band last announced and not yet filled
        if hub:
            hub.meta(symbol, self.size)

    def on_bar(self, bar: Bar) -> None:
        end = bar.end
        m = rth_minute(end)
        if m is None:
            return
        if self.hub:  # the panel also shows the open bar, tick by tick
            self.hub.bar(self.symbol, bar, m)
        if not bar.closed or m in self.bars and self.day == end.astimezone(ET).date():
            return
        if self.day != end.astimezone(ET).date():
            self.day, self.bars, self.band, self.alerted = end.astimezone(ET).date(), {}, None, None
        delta = bar.delta
        self.bars[m] = (bar.high, bar.low, delta)
        live = bar.realtime  # backfilled bars only rebuild the state, without alerts
        hhmm = end.astimezone(ET).strftime("%H:%M")
        self.log({"event": "bar", "symbol": self.symbol, "time": hhmm, "close": bar.close, "delta": delta,
                  "cum_delta": sum(b[2] for b in self.bars.values())})
        band = single_print_band([(k, h, l) for k, (h, l, _) in self.bars.items()], self.size)
        name = self.symbol.lstrip("@")
        # The profile's price buckets start at the day's low, so a new low shifts every bucket and the band's
        # edges move by a fraction of a bucket. Treat a band that overlaps the one already announced as the same
        # band (no new alert), and call it filled only when price actually trades back into it.
        if band and band != self.band:
            self.log({"event": "band", "symbol": self.symbol, "time": hhmm, "low": band[0], "high": band[1]})
            if live and not (self.alerted and overlaps(band, self.alerted)):
                self.notify(f"{name} {hhmm} 出现单印区 {price(band[0])}–{price(band[1])}（双分布形态）")
        if band:
            self.alerted = band   # backfilled bands count as announced too: no alert for an old band at start
        elif self.band and self.alerted:
            if overlaps((bar.low, bar.high), self.alerted):
                self.log({"event": "band_filled", "symbol": self.symbol, "time": hhmm, "low": self.alerted[0], "high": self.alerted[1]})
                if live:
                    self.notify(f"{name} {hhmm} 单印区 {price(self.alerted[0])}–{price(self.alerted[1])} 已回补")
                self.alerted = None
            else:   # gone only because the buckets shifted; price never came back
                self.log({"event": "band_gone", "symbol": self.symbol, "time": hhmm})
        if self.hub and band != self.band:
            self.hub.band(self.symbol, band)
        self.band = band

    def run(self, source: BarSource, stop: threading.Event, listeners=()) -> None:
        """Follow the source's bars, reconnecting when they stop. Each connection backfills from 08:00 ET:
        the profile uses only RTH bars, but MFI needs pre-market bars to have a value at the open.
        `listeners` get every bar too (pre-market included)."""
        while not stop.is_set():
            try:
                since = dt.datetime.now(ET).replace(hour=8, minute=0, second=0, microsecond=0)
                for bar in source.stream(self.symbol, since):
                    if stop.is_set():
                        return
                    for listen in listeners:
                        listen(bar)
                    self.on_bar(bar)
                self.log({"event": "stream_end", "symbol": self.symbol})
            except Exception as exc:
                self.log({"event": "stream_error", "symbol": self.symbol, "error": str(exc)})
            stop.wait(5)


def mac_notify(text: str) -> None:
    script = f"display notification {json.dumps(text)} with title \"订单流提醒\" sound name \"Glass\""
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orderflow-alert", description="Read-only delta and single-print (double distribution) alerts on NQ/ES.")
    parser.add_argument("--symbol", action="append", metavar="SYMBOL", help="NQ/ES/MNQ/MES symbol to watch (repeatable; default @MNQ and @MES)")
    parser.add_argument("--no-notify", action="store_true", help="only print JSON lines, no macOS notifications")
    parser.add_argument("--port", type=int, default=8765, help="local panel port (default 8765); 0 = no panel")
    parser.add_argument("--no-browser", action="store_true", help="serve the panel without opening it in the browser")
    parser.add_argument("--mfi-minutes", type=int, default=5, metavar="N", help="bar size for the MFI(14) 20/80 alerts, in minutes (default 5)")
    parser.add_argument("--no-mfi", action="store_true", help="turn off the MFI alerts")
    dc = parser.add_argument_group("discord", "also post every alert to a Discord channel through a bot")
    dc.add_argument("--discord-channel", metavar="ID", help="channel ID to post alerts to")
    dc.add_argument("--discord-token-file", metavar="PATH", help="file with the bot token (DISCORD_BOT_TOKEN=... or the token alone)")
    dc.add_argument("--discord-mention", metavar="USER_ID", default="", help="user ID to mention in each alert")
    parser.add_argument("--source", choices=["auto", "tradestation", "ibkr"], default="auto",
                        help="where the bars come from. auto (default): TradeStation if logged in, else IBKR if ib_async is installed")
    ib = parser.add_argument_group("ibkr", "connection to a running TWS or IB Gateway (API enabled)")
    ib.add_argument("--ib-host", default="127.0.0.1")
    ib.add_argument("--ib-port", type=int, default=7496, help="TWS live 7496 / paper 7497; IB Gateway live 4001 / paper 4002 (default 7496)")
    ib.add_argument("--ib-client-id", type=int, default=17, help="API client ID, unique among programs connected to TWS (default 17)")
    return parser


def pick_source(requested: str) -> tuple[str, str]:
    """Which source to use, and why. An explicit --source always wins; auto prefers a TradeStation login, then IBKR."""
    if requested != "auto":
        return requested, "chosen with --source"
    from .tradestation import CREDENTIALS
    if CREDENTIALS.exists():
        return "tradestation", "auto: TradeStation login found"
    try:
        import ib_async  # noqa: F401
    except ImportError:
        raise SystemExit("No data source set up. Either\n"
                         "  TradeStation: run orderflow-login once, or\n"
                         "  IBKR: pip install 'orderflow-alert[ibkr]' and start TWS / IB Gateway with the API enabled.")
    return "ibkr", "auto: no TradeStation login, ib_async installed"


def make_source(args) -> tuple[BarSource, str]:
    name, why = pick_source(args.source)
    if name == "ibkr":
        from .ibkr import IBKRSource
        return IBKRSource(args.ib_host, args.ib_port, args.ib_client_id), why
    from .tradestation import TradeStationSource
    return TradeStationSource(), why


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source, why = make_source(args)
    except SystemExit as exc:   # missing credentials / missing optional package: explain and exit
        print(exc, file=sys.stderr)
        return 78
    hub = Hub() if args.port else None
    discord = None
    if args.discord_channel:
        if not args.discord_token_file:
            print("--discord-channel needs --discord-token-file", file=sys.stderr)
            return 64
        from .discord import DiscordPoster
        discord = DiscordPoster(args.discord_channel, args.discord_token_file, args.discord_mention)

    def notify(text: str) -> None:
        if not args.no_notify:
            mac_notify(text)
        if discord:
            discord.post(text)
        if hub:
            hub.alert(text)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    for symbol in args.symbol or ["@MNQ", "@MES"]:
        listeners = [] if args.no_mfi else [MfiWatcher(symbol, notify, minutes=args.mfi_minutes).on_bar]
        threading.Thread(target=FlowWatcher(symbol, notify, hub=hub).run, args=(source, stop, listeners), daemon=True).start()
    print(f"flow alert started: {source.name} ({why})", file=sys.stderr, flush=True)
    if hub:
        serve_panel(hub, args.port)
        url = f"http://127.0.0.1:{args.port}/"
        print(f"panel: {url}", file=sys.stderr, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
    while not stop.is_set():
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
