import datetime as dt

from orderflow_alert.bars import Bar
from orderflow_alert.mfi import ET, MfiWatcher, crossing, in_session, money_flow


def et(hh, mm, day=19):
    return dt.datetime(2026, 11, day, hh, mm, tzinfo=ET)


def one_min(end, close, volume=100, realtime=True, high=None, low=None):
    return Bar(end=end, open=close, high=high if high is not None else close, low=low if low is not None else close,
               close=close, buy_volume=0, sell_volume=0, closed=True, realtime=realtime, volume=volume)


def test_crossing_rules():
    assert crossing(25, 19) == "跌破 20"
    assert crossing(19, 20) == "回升穿过 20"
    assert crossing(80, 81) == "涨破 80"
    assert crossing(81, 80) == "回落穿过 80"
    assert crossing(50, 60) is None and crossing(15, 18) is None and crossing(85, 90) is None
    assert crossing(None, 10) is None                       # no previous value yet: no alert


def test_money_flow_extremes():
    up = [one_min(et(9, 31 + i), 100 + i) for i in range(16)]
    assert money_flow(up)[-1] == 100.0                      # typical price only rises
    assert money_flow(up)[13] is None                       # needs 14 bars that each have a previous bar
    down = [one_min(et(9, 31 + i), 100 - i) for i in range(16)]
    assert money_flow(down)[-1] == 0.0


def test_five_minute_bars_align_to_the_clock_and_ignore_repeats():
    logs = []
    w = MfiWatcher("@MES", lambda t: None, logs.append)
    for m in range(31, 41):                                 # 1-minute bars ending 09:31 … 09:40
        w.on_bar(one_min(et(9, m), 7600 + m, high=7700, low=7500, volume=10))
    w.on_bar(one_min(et(9, 35), 1, volume=999))             # a repeat from reconnect backfill: ignored
    assert [b.end.astimezone(ET).strftime("%H:%M") for b in w.bars] == ["09:35", "09:40"]
    first = w.bars[0]
    assert (first.open, first.close, first.high, first.low, first.volume) == (7631, 7635, 7700, 7500, 50)


def test_missing_minute_still_closes_the_bucket():
    w = MfiWatcher("@MES", lambda t: None, lambda e: None)
    w.on_bar(one_min(et(9, 31), 1))
    w.on_bar(one_min(et(9, 33), 2))                         # 09:34 and 09:35 never arrive
    w.on_bar(one_min(et(9, 36), 3))                         # first minute of the next bucket
    assert [b.end.astimezone(ET).strftime("%H:%M") for b in w.bars] == ["09:35"]
    assert w.bars[0].close == 2


def feed_five_minute_closes(w, closes, start=et(8, 0), realtime=True):
    """One 1-minute bar per 5-minute bucket end, so each 5-minute bar closes at the given price."""
    t = start
    for c in closes:
        t += dt.timedelta(minutes=5)
        for k in range(4, -1, -1):
            w.on_bar(one_min(t - dt.timedelta(minutes=k), c, volume=100, realtime=realtime))


def test_alerts_on_entering_and_leaving_the_zones_only_in_session():
    seen = []
    w = MfiWatcher("@MNQ", seen.append, lambda e: None)
    # pre-market warm-up (08:05 … 09:30): steady rise, MFI 100 — no alerts outside the session
    feed_five_minute_closes(w, [100 + i for i in range(18)])
    assert seen == []
    # session: fall hard (MFI drops through 80 then 20), then rise (back above 20, then above 80)
    feed_five_minute_closes(w, [90 - 3 * i for i in range(16)] + [50 + 5 * i for i in range(16)], start=et(9, 30))
    kinds = [s.split("MFI ")[1].split("（")[0] for s in seen]
    assert kinds == ["回落穿过 80", "跌破 20", "回升穿过 20", "涨破 80"]
    # MFI weighs flow by price: the higher-priced rising bars still outweigh 3 falling ones, so 80 breaks on the 4th
    # falling bar (09:50): 10 rising bars at ~112 against 4 falling at ~85.5 gives 76.6
    assert seen[0] == "MNQ 5分钟 MFI 回落穿过 80（76.7）· 09:50"


def test_no_alerts_for_backfilled_bars():
    seen = []
    w = MfiWatcher("@MES", seen.append, lambda e: None)
    feed_five_minute_closes(w, [100 + i for i in range(18)], realtime=False)
    feed_five_minute_closes(w, [90 - 3 * i for i in range(16)], start=et(9, 30), realtime=False)
    assert seen == []


def test_in_session():
    assert in_session(et(9, 35)) and in_session(et(16, 0))
    assert not in_session(et(9, 30)) and not in_session(et(16, 5)) and not in_session(et(10, 0, day=21))   # Saturday
