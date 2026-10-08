"""Daily chart attached to the AI Analysis Complete email."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image

from apps.api.app.notifications.chart_image import render_outlook_chart
from test_notifications import NOW, TRADE_WORDS, FakeSMTP, _body, _db, _recipient, _store, env  # noqa: F401
from test_outlook_alert import ON_TIME, _publish  # noqa: F401


def _bars(n=40, start=1.10):
    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    out, px = [], start
    for i in range(n):
        o = px
        c = px + (0.0004 if i % 5 else -0.0009)
        out.append({"t": (t0 + timedelta(days=i)).isoformat(), "o": o, "h": max(o, c) + 0.0006, "l": min(o, c) - 0.0006, "c": c})
        px = c
    return out


def test_daily_chart_is_a_png_with_both_candle_colours():
    bars = _bars()
    last = bars[-1]["t"]
    png = render_outlook_chart(
        "EURUSD", bars, digits=5, direction="BULLISH", confidence=72, rank=1,
        erz=(1.1010, 1.1020), targets=[1.1080, 1.1120], invalidation=1.0960,
        channel={"upper": [[bars[4]["t"], 1.104], [last, 1.109]], "mid": [[bars[4]["t"], 1.101], [last, 1.106]],
                 "lower": [[bars[4]["t"], 1.098], [last, 1.103]]},
        path=[[bars[10]["t"], bars[10]["c"]], [last, bars[-1]["c"]],
              [(datetime(2026, 9, 20, tzinfo=timezone.utc)).isoformat(), 1.112]],
    )
    assert png.startswith(b"\x89PNG")
    im = Image.open(BytesIO(png))
    assert im.size == (1280, 800)
    colours = im.getcolors(im.size[0] * im.size[1])
    assert any(c == (11, 183, 124) for _, c in colours)
    assert any(c == (240, 68, 68) for _, c in colours)


def test_a_short_history_is_not_drawn():
    try:
        render_outlook_chart("EURUSD", _bars(5))
    except ValueError:
        return
    raise AssertionError("expected a short history to be refused")


def test_no_candles_means_no_chart_and_the_email_still_sends(env):
    from apps.api.app.notifications.outlook_charts import chart_images
    from apps.api.app.notifications.worker import dispatch

    _recipient()
    assert _publish(published_at=ON_TIME)["queued"] == 1
    with _db() as conn:
        event = _store(conn).events()[0]
    assert chart_images(event) == []
    assert dispatch(NOW)["sent"] == 1
    msg = FakeSMTP.all_sent()[0]
    assert "cid:chart-" not in _body(msg)
    assert [p for p in msg.walk() if p.get_content_type() == "image/png"] == []


def test_email_embeds_one_chart_per_qualified_symbol(env, monkeypatch):
    from apps.api.app.notifications import outlook_charts
    from apps.api.app.notifications.worker import dispatch

    blob = render_outlook_chart("EURUSD", _bars(), direction="BULLISH", rank=1, erz=(1.10, 1.101), targets=[1.105], invalidation=1.09)
    monkeypatch.setattr(outlook_charts, "chart_images", lambda event: [("chart-EURUSD", blob, "EURUSD"), ("chart-GBPUSD", blob, "GBPUSD")])
    _recipient()
    _publish()
    assert dispatch(NOW)["sent"] == 1
    msg = FakeSMTP.all_sent()[0]
    html = next(p.get_content() for p in msg.walk() if p.get_content_type() == "text/html")
    assert html.index("cid:chart-EURUSD") < html.index("cid:chart-GBPUSD")
    assert "AUDCAD" not in html
    assert "D1 charts for EURUSD, GBPUSD" in _body(msg)
    images = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert {p["Content-ID"] for p in images} == {"<chart-EURUSD>", "<chart-GBPUSD>"}
    assert all(p.get_content_disposition() == "inline" for p in images)
    assert not TRADE_WORDS.search(_body(msg))


def test_a_chart_failure_still_sends_the_email(env, monkeypatch):
    from apps.api.app.notifications import outlook_charts
    from apps.api.app.notifications.worker import dispatch

    def boom(event):
        raise RuntimeError("chart down")

    monkeypatch.setattr(outlook_charts, "chart_images", boom)
    _recipient()
    _publish()
    assert dispatch(NOW)["sent"] == 1
    msg = FakeSMTP.all_sent()[0]
    assert "AI Analysis Complete" in msg["Subject"]
    assert [p for p in msg.walk() if p.get_content_type() == "image/png"] == []
