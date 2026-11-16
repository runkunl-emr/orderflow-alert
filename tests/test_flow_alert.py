import datetime as dt
import json
import urllib.request

from orderflow_alert.flow_alert import ET, FlowWatcher, Hub, bucket, rth_minute, serve_panel, single_print_band
from orderflow_alert.tradestation import to_bar


def feed(w, m):
    """Messages are written in TradeStation's stream format and go through its adapter, as in production."""
    bar = to_bar(m)
    if bar:
        w.on_bar(bar)


def msg(day, hhmm, high, low, up=10, down=5, live=True, status="Closed"):
    h, m = map(int, hhmm.split(":"))
    end = dt.datetime(2026, 11, day, h, m, tzinfo=ET).astimezone(dt.timezone.utc)
    return {"TimeStamp": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "Open": str(high), "High": str(high), "Low": str(low), "Close": str(low),
            "UpVolume": up, "DownVolume": down, "BarStatus": status, "IsRealtime": live}


def test_bucket_and_rth_minute():
    assert bucket("@MNQ") == bucket("NQZ26") == 5.0
    assert bucket("@MES") == bucket("ESZ26") == 1.25
    assert rth_minute(dt.datetime(2026, 11, 12, 9, 31, tzinfo=ET)) == 0
    assert rth_minute(dt.datetime(2026, 11, 12, 16, 0, tzinfo=ET)) == 389
    assert rth_minute(dt.datetime(2026, 11, 12, 9, 30, tzinfo=ET)) is None
    assert rth_minute(dt.datetime(2026, 11, 14, 10, 0, tzinfo=ET)) is None  # Saturday


def test_single_print_band_between_two_distributions():
    # periods 0-1 balance at 100-110, period 2 runs 110-150 alone, periods 3-4 balance at 150-160
    bars = [(0, 110, 100), (30, 110, 100), (60, 150, 110), (90, 160, 150), (120, 160, 150)]
    assert single_print_band(bars, 5.0) == (115.0, 150.0)


def test_no_band_on_balanced_or_trending_day():
    assert single_print_band([(0, 110, 100), (30, 112, 101), (60, 109, 102)], 5.0) is None
    # a trend whose periods overlap leaves no single prints between doubled prices
    assert single_print_band([(0, 110, 100), (30, 120, 105), (60, 130, 112)], 5.0) is None
    # single prints reaching the day's high have nothing doubled above them
    assert single_print_band([(0, 110, 100), (30, 110, 100), (60, 150, 112)], 5.0) is None


def test_watcher_alerts_once_on_live_band_then_on_fill():
    seen, logs = [], []
    w = FlowWatcher("@MNQ", seen.append, logs.append)
    for t, h, l in (("09:31", 110, 100), ("10:01", 110, 100), ("10:31", 150, 110)):
        feed(w, msg(12, t, h, l))
    assert seen == []  # the run still reaches the day's high
    feed(w, msg(12, "11:01", 160, 150))  # a new period builds above it, sharing the 150 bucket
    feed(w, msg(12, "11:01", 160, 150))  # repeated closed bar (reconnect backfill) is ignored
    assert seen == ["MNQ 11:01 出现单印区 115–150（双分布形态）"]
    feed(w, msg(12, "11:31", 160, 150))
    assert len(seen) == 1  # same band, no repeat
    feed(w, msg(12, "12:01", 150, 105))  # a later period trades back through the band
    assert seen[-1] == "MNQ 12:01 单印区 115–150 已回补"
    assert [e["cum_delta"] for e in logs if e["event"] == "bar"] == [5, 10, 15, 20, 25, 30]


def test_backfill_open_bars_and_new_day():
    seen = []
    w = FlowWatcher("@MES", seen.append, lambda e: None)
    feed(w, msg(12, "09:45", 7600, 7590, status="Open"))
    feed(w, {"Heartbeat": 1})
    assert w.bars == {}
    for t, h, l in (("09:31", 7610, 7600), ("10:01", 7610, 7600), ("10:31", 7650, 7610), ("11:01", 7660, 7650), ("11:31", 7660, 7650)):
        feed(w, msg(12, t, h, l, live=False))
    assert w.band is not None and seen == []  # backfill rebuilds state without alerting
    feed(w, msg(13, "09:31", 7620, 7615))
    assert w.day == dt.date(2026, 11, 13) and list(w.bars) == [0] and w.band is None


def test_hub_replays_today_and_resets_on_new_day():
    hub = Hub()
    w = FlowWatcher("@MNQ", lambda text: None, lambda e: None, hub=hub)
    feed(w, msg(12, "09:32", 110, 100, status="Open"))
    feed(w, msg(12, "09:32", 112, 100, up=30, down=10))  # same bar, now closed: replaces the open one
    feed(w, msg(12, "09:31", 105, 101))
    hub.alert("MNQ test")
    q, snapshot = hub.subscribe()
    assert [e["type"] for e in snapshot] == ["meta", "bar", "bar", "alert"]
    bars = [e for e in snapshot if e["type"] == "bar"]
    assert [b["minute"] for b in bars] == [0, 1] and bars[1]["high"] == 112 and bars[1]["delta"] == 20
    # chart time is the bar's start in ET wall-clock: 09:31 for the bar ending 09:32
    assert dt.datetime.fromtimestamp(bars[1]["time"], dt.timezone.utc).strftime("%H:%M") == "09:31"
    feed(w, msg(13, "09:31", 120, 115))
    assert q.get_nowait() == {"type": "reset", "symbol": "@MNQ"}
    assert q.get_nowait()["minute"] == 0
    hub.unsubscribe(q)
    assert hub.clients == []


def test_panel_serves_page_and_event_stream():
    hub = Hub()
    hub.meta("@MES", 1.25)
    server = serve_panel(hub, 0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"lightweight-charts" in urllib.request.urlopen(base + "/").read()
        with urllib.request.urlopen(base + "/events", timeout=5) as r:
            assert json.loads(r.readline().decode().removeprefix("data: ")) == {"type": "meta", "symbol": "@MES", "bin": 1.25}
    finally:
        server.shutdown()


def test_pick_source(monkeypatch, tmp_path):
    import sys

    import pytest

    from orderflow_alert import tradestation
    from orderflow_alert.flow_alert import pick_source

    creds = tmp_path / "tradestation.json"
    monkeypatch.setattr(tradestation, "CREDENTIALS", creds)
    assert pick_source("ibkr")[0] == "ibkr"                       # explicit choice always wins
    assert pick_source("tradestation")[0] == "tradestation"
    assert pick_source("auto")[0] == "ibkr"                       # no TradeStation login, ib_async installed (dev extra)
    creds.write_text("{}")
    assert pick_source("auto")[0] == "tradestation"               # a TradeStation login wins
    creds.unlink()
    monkeypatch.setitem(sys.modules, "ib_async", None)            # simulate ib_async not installed
    with pytest.raises(SystemExit, match="No data source set up"):
        pick_source("auto")
