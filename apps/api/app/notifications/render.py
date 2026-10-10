"""Email rendering: subject, responsive HTML and plain-text fallback for alert events and the SMTP test message.

Alerts describe market structure only — never an executed trade, an order or a position change."""
from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from zoneinfo import ZoneInfo

from ..market.channel_events import provider_label
from .smtp import SmtpConfig
from .store import ALERT_TYPES

LAGOS = ZoneInfo("Africa/Lagos")
BRAND = "Cacsms Traders"
FOOTER = "This is an automated market intelligence alert."
SAFETY = "Analysis only — no order has been placed, modified or closed. Operating mode: ANALYSIS ONLY."
TEST_SUBJECT = "[Cacsms Traders] Email Notification Test"
TEST_BODY = "Cacsms Traders email notification service is configured successfully."
TONE = {"BULLISH": "#067647", "BEARISH": "#b42318"}


def _dp(symbol: str) -> int:
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


def _px(value, symbol: str) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{_dp(symbol)}f}"
    except (TypeError, ValueError):
        return str(value)


def _time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{t.strftime('%a %d %b %Y %H:%M')} UTC · {t.astimezone(LAGOS).strftime('%H:%M')} WAT"


def _title(word: str | None) -> str:
    return (word or "—").replace("_", " ").title()


def _day(value: str | None) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%a %d %b %Y") if value else "—"
    except ValueError:
        return value or "—"


def _wat(value: str | None) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(LAGOS).strftime("%H:%M WAT") if value else "—"
    except ValueError:
        return value or "—"


def app_link(path: str) -> str | None:
    base = os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
    if not base and os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip():
        base = "https://" + os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip().rstrip("/")
    return f"{base}/#/{path}" if base.startswith(("https://", "http://")) else None


def subject(e: dict) -> str:
    sym, tf, t, m = e["symbol"], e.get("timeframe") or "", e["event_type"], e.get("metadata") or {}
    if t == "AI_OUTLOOK_EVENT":
        life = (m.get("lifecycle") or "update").replace("_", " ").title()
        return f"[{BRAND}] {sym} — Outlook {life}"
    if t == "AI_OUTLOOK_PUBLISHED":
        n = (m.get("counts") or {}).get("qualified", 0)
        return (f"[{BRAND}] {'[Late] ' if m.get('late') else ''}AI Analysis Complete — Outlook for {_day(m.get('outlook_for'))} "
                f"({n} qualified {'opportunity' if n == 1 else 'opportunities'})")
    if t == "CHANNEL_BREAK":
        return f"[{BRAND}] {sym} {tf} — {_title(e.get('direction'))} Channel Break"
    if t == "CHANNEL_TOUCH":
        return f"[{BRAND}] {sym} {tf} — {'Upper' if m.get('boundary') == 'UPPER' else 'Lower'} Channel Touch"
    if t == "BREAK_RETEST_CONTINUATION":
        return f"[{BRAND}] {sym} {tf} — Break & Retest Continuation"
    if t == "TIT_DETECTED":
        return f"[{BRAND}] {sym} — TiT {e.get('tit_level') or ''} Detected".replace("  ", " ")
    return f"[{BRAND}] {sym} — {ALERT_TYPES.get(t, t)}"


def _alert_label(e: dict) -> str:
    m = e.get("metadata") or {}
    t = e["event_type"]
    if t == "CHANNEL_TOUCH":
        return m.get("label") or "Channel Touch"
    if t == "BREAK_RETEST_CONTINUATION":
        return m.get("label") or "Trend Continuation"
    if t == "TIT_DETECTED":
        return f"Trend-in-Trend {e.get('tit_level') or ''}".strip()
    if e["event_type"] == "AI_OUTLOOK_EVENT":
        return f"Outlook {(m.get('lifecycle') or 'update').replace('_', ' ').title()}"
    return f"{_title(e.get('direction'))} Channel Break"


def summary_rows(e: dict) -> list[tuple[str, str]]:
    sym, m = e["symbol"], e.get("metadata") or {}
    ctx = m.get("context") or {}
    context = ctx.get("summary") or m.get("summary") or m.get("trend_context") or "—"
    if e["event_type"] == "TIT_DETECTED":
        context = f"{m.get('parent_tf')} parent {_title(m.get('htf_direction'))} · {m.get('counter_trend_tf')} {str(m.get('phase') or '').lower()}"
    return [
        ("Alert type", _alert_label(e)),
        ("Symbol", sym),
        ("Timeframe", e.get("timeframe") or "—"),
        ("Direction", _title(e.get("direction"))),
        ("Price", _px(e.get("price"), sym)),
        ("Event level", _px(e.get("level"), sym)),
        ("Market / structural context", context),
        ("Event time", _time(e.get("event_time"))),
        ("Data provider", provider_label(e.get("provider"))),
    ]


def detail_rows(e: dict) -> list[tuple[str, str]]:
    sym, m, t = e["symbol"], e.get("metadata") or {}, e["event_type"]
    px = lambda k: _px(m.get(k), sym)  # noqa: E731
    if t == "CHANNEL_BREAK":
        return [("Channel type", m.get("channel_type") or "—"), ("Channel ID", e.get("channel_id") or "—"),
                ("Upper boundary", px("upper_boundary")), ("Lower boundary", px("lower_boundary")),
                ("Broken boundary", px("break_level")), ("Break price (close)", px("break_price")),
                ("Break candle close", _time(m.get("break_candle_close"))),
                ("Confirmation", f"{m.get('closes_beyond')} closed {e.get('timeframe')} candles beyond the boundary "
                                 f"(rule: {m.get('confirm_closes')})"),
                ("Detected", _time(e.get("detected_at")))]
    if t == "CHANNEL_TOUCH":
        dist_atr = m.get("distance_atr")
        return [("Boundary", f"{'Upper' if m.get('boundary') == 'UPPER' else 'Lower'} channel boundary"),
                ("Boundary level", px("boundary_level")), ("Touch price", px("touch_price")), ("Candle close", px("close")),
                ("Distance to boundary", f"{_px(m.get('distance'), sym)}" + (f" ({dist_atr} ATR)" if dist_atr is not None else "")),
                ("Touch tolerance", f"{px('tolerance')} ({m.get('tolerance_atr')} × ATR)"),
                ("Trend direction", _title({"UPTREND": "Bullish", "DOWNTREND": "Bearish"}.get(m.get("trend_direction"), "Ranging"))),
                ("Channel status", m.get("channel_status") or "—"),
                ("Channel range", f"{px('lower_boundary')} – {px('upper_boundary')}"),
                ("Detected", _time(e.get("detected_at")))]
    if t == "BREAK_RETEST_CONTINUATION":
        return [("Continuation", m.get("label") or "—"), ("Break level", px("break_level")), ("Break time", _time(m.get("break_time"))),
                ("Retest price", px("retest_price")), ("Retest time", _time(m.get("retest_time"))),
                ("Continuation candle close", _time(m.get("continuation_close"))),
                ("Trend context", m.get("trend_context") or "—"), ("Confirmation state", m.get("confirmation_state") or "—"),
                ("Detected", _time(e.get("detected_at")))]
    if t == "TIT_DETECTED":
        zone = m.get("zone") or [None, None]
        layers = " · ".join(f"{l.get('id')} {l.get('tf')}: {(l.get('trend') or {}).get('label', 'n/a')}"
                            f"{' (' + l['alignment'] + ')' if l.get('alignment') and l.get('alignment') != '—' else ''}"
                            for l in m.get("layers") or [] if l.get("available"))
        return [("TiT level", e.get("tit_level") or "—"), ("HTF direction", _title({"UPTREND": "Bullish", "DOWNTREND": "Bearish"}.get(m.get("htf_direction"), "—"))),
                ("Parent timeframe", f"{m.get('parent_layer')} {m.get('parent_tf')} ({m.get('parent_state') or '—'})"),
                ("Counter-trend timeframe", f"{m.get('counter_trend_tf')} — {m.get('counter_trend_type')}, {m.get('phase')} ({m.get('maturity')}% mature)"),
                ("Current price", _px(e.get("price"), sym)), ("Relevant zone", f"{_px(zone[0], sym)} – {_px(zone[1], sym)}"),
                ("Channel rejoin level", px("rejoin_level")), ("Objective 1 / 2", f"{px('objective_1')} / {px('objective_2')}"),
                ("Invalidation", px("invalidation")), ("Layers", layers or "—"),
                ("Detection reason", m.get("reason") or m.get("summary") or "—"), ("Detected", _time(e.get("detected_at")))]
    return []


def _table(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td style="padding:9px 14px;border-bottom:1px solid #edf1f7;color:#5b6b82;font-size:12px;text-transform:uppercase;'
        f'letter-spacing:.04em;width:38%;vertical-align:top">{html.escape(k)}</td>'
        f'<td style="padding:9px 14px;border-bottom:1px solid #edf1f7;color:#10203d;font-size:14px;font-weight:600">{html.escape(str(v))}</td></tr>'
        for k, v in rows)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{cells}</table>'


def _chart_row(symbol: str, cid: str, caption: str = "D1 chart · channel, expected reaction zone, targets and invalidation") -> str:
    alt = f"{symbol} chart — {caption}"
    return (
        f'<tr><td style="padding:2px 22px 16px">'
        f'<img src="cid:{html.escape(cid, quote=True)}" alt="{html.escape(alt)}" width="596" '
        f'style="display:block;width:100%;max-width:596px;height:auto;border:1px solid #e1e8f2;border-radius:10px" />'
        f'<div style="margin-top:6px;color:#5b6b82;font-size:12px;line-height:1.5">{html.escape(caption)}</div></td></tr>'
    )


def _html(title: str, tone: str, sections: list[tuple[str, list[tuple[str, str]]]], intro: str | None = None,
          link: tuple[str, str] | None = None, images: dict[str, str] | None = None,
          lead: tuple[str, str, str] | None = None) -> str:
    images = images or {}
    blocks = []
    for name, rows in sections:
        if not rows:
            continue
        blocks.append(
            f'<tr><td style="padding:18px 22px 6px;font-size:13px;font-weight:700;color:#10203d;text-transform:uppercase;letter-spacing:.06em">'
            f'{html.escape(name)}</td></tr>')
        cid = next((images[sym] for sym in images if f" {sym} " in f" {name} "), None)
        sym = next((sym for sym in images if f" {sym} " in f" {name} "), None)
        if cid and sym:
            blocks.append(_chart_row(sym, cid))
        blocks.append(f'<tr><td style="padding:0 8px 8px">{_table(rows)}</td></tr>')
    body = "".join(blocks)
    intro_html = f'<tr><td style="padding:18px 22px 0;font-size:15px;color:#10203d">{html.escape(intro)}</td></tr>' if intro else ""
    if link:
        body += (f'<tr><td style="padding:10px 22px 18px"><a href="{html.escape(link[1], quote=True)}" style="display:inline-block;padding:10px 18px;'
                 f'border-radius:8px;background:#1765ef;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none">{html.escape(link[0])}</a></td></tr>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f2f5fa;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f5fa;padding:24px 10px">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e1e8f2">
<tr><td style="background:#0b1f3f;padding:22px">
<div style="color:#ffffff;font-size:18px;font-weight:800;letter-spacing:.14em">CACSMS TRADERS</div>
<div style="color:#9fb4d6;font-size:12px;margin-top:4px;letter-spacing:.04em">Autonomous Market Intelligence Alert</div>
</td></tr>
<tr><td style="padding:18px 22px 0"><div style="display:inline-block;padding:6px 12px;border-radius:999px;background:{tone}14;color:{tone};font-size:13px;font-weight:700">{html.escape(title)}</div></td></tr>
{(_chart_row(*lead) if lead else "")}
{intro_html}
{body}
<tr><td style="padding:16px 22px 22px;color:#5b6b82;font-size:12px;line-height:1.6;border-top:1px solid #edf1f7">
{html.escape(FOOTER)}<br>{html.escape(SAFETY)}
</td></tr>
</table></td></tr></table></body></html>"""


def _text(title: str, sections: list[tuple[str, list[tuple[str, str]]]], intro: str | None = None,
          link: tuple[str, str] | None = None) -> str:
    lines = ["CACSMS TRADERS", "Autonomous Market Intelligence Alert", "", title, ""]
    if intro:
        lines += [intro, ""]
    for name, rows in sections:
        if not rows:
            continue
        lines += [name.upper(), *[f"{k.upper()}: {v}" for k, v in rows], ""]
    if link:
        lines += [f"{link[0]}: {link[1]}", ""]
    lines += [FOOTER, SAFETY]
    return "\n".join(lines)


def _message(cfg: SmtpConfig, to: str, subj: str, text: str, html_body: str, headers: dict[str, str] | None = None,
             images: list[tuple[str, bytes]] | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = to
    msg["Subject"] = subj
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=(cfg.from_email.split("@")[-1] or "cacsms-traders"))
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    if images:
        html_part = msg.get_payload()[1]
        for cid, blob in images:
            html_part.add_related(blob, maintype="image", subtype="png", cid=f"<{cid}>")
            image = html_part.get_payload()[-1]
            image.replace_header("Content-Disposition", f'inline; filename="{cid}.png"')
    return msg


def outlook_sections(e: dict) -> tuple[str, list[tuple[str, list[tuple[str, str]]]]]:
    m = e.get("metadata") or {}
    c = m.get("counts") or {}
    asian = _wat(m.get("asian_open"))
    timing = (f"Late — completed after market open (Asian session opened {asian})" if m.get("late")
              else f"On time — ready before market open (Asian session opens {asian})")
    summary = [
        ("Analysis", f"{ {'DAILY': 'D1', 'WEEKLY': 'W1', 'MONTHLY': 'MN', 'H8': 'H8'}.get(m.get('horizon') or '', 'D1') } close of {_day(m.get('analysis_date'))}"),
        ("Outlook for", _day(m.get("outlook_for"))),
        ("Completed", _time(m.get("published_at"))),
        ("Timing", timing),
        ("Instruments analysed", f"{c.get('published', 0)} of {m.get('total') or '—'}"),
        ("Qualified opportunities", str(c.get("qualified", 0))),
        ("Insufficient data / failed", f"{c.get('insufficient', 0)} / {c.get('failed', 0)}"),
        ("Data provider", provider_label(e.get("provider"))),
    ]
    sections = [("Analysis summary", summary)]
    for o in m.get("opportunities") or []:
        sym = o.get("symbol") or ""
        conf = o.get("confidence")
        head = f"#{o.get('rank') or '—'} {sym} — {_title(o.get('direction'))}" + (f" ({float(conf):.0f}% confidence)" if conf is not None else "")
        lo, hi = (o.get("erz") or [None, None])[:2]
        score = o.get("score")
        sections.append((head, [
            ("Expected next move", o.get("next_move") or "—"),
            ("Expected reaction zone (ERZ)", f"{_px(lo, sym)} – {_px(hi, sym)}"),
            ("Targets", " / ".join(_px(t, sym) for t in o.get("targets") or []) or "—"),
            ("Invalidation", _px(o.get("invalidation"), sym)),
            ("Opportunity score", f"{float(score):.0f}" if score is not None else "—"),
        ]))
    if not m.get("opportunities"):
        sections.append(("Opportunities", [("Qualified opportunities", "None today — no instrument met the qualification threshold")]))
    intro = ("Today's AI market analysis finished after the market opened. The outlook below is still available for review."
             if m.get("late") else "Today's AI market analysis is complete and ready for review before the market opens.")
    return intro, sections


def outlook_message(cfg: SmtpConfig, e: dict, to: str) -> EmailMessage:
    import logging

    from .outlook_charts import chart_images

    m = e.get("metadata") or {}
    title = ("Late · " if m.get("late") else "") + "AI Analysis Complete"
    intro, sections = outlook_sections(e)
    url = app_link("ai-market-outlook/daily")
    link = ("Open AI Market Outlook", url) if url else None
    tone = "#b54708" if m.get("late") else "#1765ef"
    try:
        shots = chart_images(e)
    except Exception:
        logging.getLogger("cacsms.notifications").warning("Outlook charts were left out of the email", exc_info=True)
        shots = []
    text = _text(title, sections, intro, link)
    if shots:
        names = ", ".join(sym for _, _, sym in shots)
        text += f"\nD1 charts for {names} are included in the HTML version of this email.\n"
    return _message(cfg, to, subject(e), text, _html(title, tone, sections, intro, link, {sym: cid for cid, _, sym in shots}),
                    {"X-Cacsms-Alert-Id": e["id"], "X-Cacsms-Alert-Type": e["event_type"]},
                    [(cid, png) for cid, png, _ in shots])


def alert_message(cfg: SmtpConfig, e: dict, to: str) -> EmailMessage:
    import logging

    if e["event_type"] == "AI_OUTLOOK_PUBLISHED":
        return outlook_message(cfg, e, to)
    title = _alert_label(e) + f" · {e['symbol']}" + (f" {e['timeframe']}" if e.get("timeframe") else "")
    sections = [("Alert summary", summary_rows(e)), ("Event details", detail_rows(e))]
    tone = TONE.get(e.get("direction") or "", "#1765ef")
    shot = None
    try:
        from .alert_charts import alert_chart

        shot = alert_chart(e)
    except Exception:
        logging.getLogger("cacsms.notifications").warning("Alert chart was left out of the email", exc_info=True)
    text = _text(title, sections)
    lead = None
    images = None
    if shot:
        cid, png, sym, caption = shot
        lead = (sym, cid, caption)
        images = [(cid, png)]
        text += f"\n{caption} for {sym} is included in the HTML version of this email.\n"
    return _message(cfg, to, subject(e), text, _html(title, tone, sections, lead=lead),
                    {"X-Cacsms-Alert-Id": e["id"], "X-Cacsms-Alert-Type": e["event_type"]}, images)


def test_message(cfg: SmtpConfig, to: str) -> EmailMessage:
    sections = [("Delivery", [("Sender", cfg.from_email), ("SMTP host", f"{cfg.host}:{cfg.port} ({cfg.security.upper()})"),
                              ("Sent", _time(datetime.now(timezone.utc).isoformat()))])]
    return _message(cfg, to, TEST_SUBJECT, _text("Email Notification Test", sections, TEST_BODY),
                    _html("Email Notification Test", "#1765ef", sections, TEST_BODY))
