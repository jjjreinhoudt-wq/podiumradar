"""Opschonen en controleren van wat er in site/data.json komt (scrape.py roept dit aan vlak voor het schrijven).

Alles wat van buiten komt (510 sites en lokaal.json van de eigen computer) is onbetrouwbaar. Hier worden tekens, lengtes,
soorten en vormen afgedwongen, zodat een rare of kwaadwillende bron nooit een kapotte of gevaarlijke data.json oplevert:
alleen bekende velden blijven over, tekst wordt van stuurtekens ontdaan en begrensd, links moeten http(s) zijn.
Een rij die niet te redden is, wordt weggelaten en geteld; is dat er te veel, dan publiceert scrape.py niets.
Test: python scraper/test_schoon.py
"""
import collections, datetime as dt, re

STUUR = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​‎‏  ‪-‮⁦-⁩﻿]")
ID = re.compile(r"^[\w-]{1,40}$")
VID = re.compile(r"^[\w-]{1,80}$")
TIJD = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
URL = re.compile(r"^https?://[^\s<>\"]+$", re.I)
VTYPES = {"pop", "concert", "arena", "cafe", "thea", "film", "museum", "festival"}
MAX_EVENTS = 80000


def tekst(s, maxlen):
    """Tekst zonder stuurtekens, met enkele spaties en begrensd; None als er niets overblijft of het geen tekst is."""
    if not isinstance(s, str):
        return None
    s = re.sub(r"\s+", " ", STUUR.sub(" ", s)).strip()
    return s[:maxlen].rstrip() or None


def datum(s, vroegst="2000-01-01", laatst=None):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", s):
        return None
    try:
        d = dt.date.fromisoformat(s)
    except ValueError:
        return None
    laatst = laatst or (dt.date.today() + dt.timedelta(days=366 * 4)).isoformat()
    return s if vroegst <= s <= laatst else None


def tijd(s):
    return s if isinstance(s, str) and TIJD.match(s) else None


def url(s):
    if not isinstance(s, str):
        return ""
    s = s.strip().replace(" ", "%20")
    return s if len(s) <= 600 and URL.match(s) else ""


def getal(x, lo, hi, cijfers=None):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or not lo <= x < hi:
        return None
    return round(x, cijfers) if cijfers is not None else int(x)


def schoon_event(e):
    """(schoon event, None) of (None, reden)."""
    if not isinstance(e, dict):
        return None, "geen object"
    if not isinstance(e.get("id"), str) or not ID.match(e["id"]):
        return None, "id"
    if not isinstance(e.get("v"), str) or not VID.match(e["v"]):
        return None, "podium-id"
    titel = tekst(e.get("title"), 200)
    if not titel:
        return None, "titel"
    d = datum(e.get("date"))
    if not d:
        return None, "datum"
    out = {"date": d, "time": tijd(e.get("time")), "title": titel, "url": url(e.get("url")),
           "genre": tekst(e.get("genre"), 40) or "Overig", "id": e["id"], "v": e["v"]}
    fs = datum(e.get("first_seen"))
    if fs:
        out["first_seen"] = fs
    p = getal(e.get("price"), 0, 10000, 2)
    if p is not None:
        out["price"] = p
    for k in ("doors", "start"):
        if tijd(e.get(k)):
            out[k] = e[k]
    if e.get("status") == "sold":
        out["status"] = "sold"
    end = datum(e.get("end"))
    if end and end >= d:
        out["end"] = end
    sup = e.get("support")
    if isinstance(sup, list):
        sup = [t for t in (tekst(x, 80) for x in sup[:8]) if t]
        if sup:
            out["support"] = sup
    dur = getal(e.get("dur"), 1, 1441)
    if dur:
        out["dur"] = dur
    ts = e.get("times")
    if isinstance(ts, list):
        ts = [{"a": a, "s": x["s"]} for x in ts[:12] if isinstance(x, dict) and tijd(x.get("s")) and (a := tekst(x.get("a"), 80))]
        if ts:
            out["times"] = ts
    if e.get("kids") is True:
        out["kids"] = True
    return out, None


def schoon_venue(v):
    if not isinstance(v, dict):
        return None
    naam = tekst(v.get("name"), 100)
    if not naam:
        return None
    return {"name": naam, "city": tekst(v.get("city"), 100) or "", "prov": tekst(v.get("prov"), 60) or "",
            "type": v.get("type") if v.get("type") in VTYPES else "pop",
            "lat": getal(v.get("lat"), -90, 90, 5), "lon": getal(v.get("lon"), -180, 180, 5)}


def schoon_alles(out):
    """Geeft (schoon data-object, {'in': n, 'weg': n, 'redenen': Counter}). Podia zonder bruikbare gegevens en events zonder podium vallen weg."""
    venues = {}
    for vid, v in (out.get("venues") or {}).items():
        sv = schoon_venue(v) if isinstance(vid, str) and VID.match(vid) else None
        if sv:
            venues[vid] = sv
    events, redenen = [], collections.Counter()
    ruw = out.get("events") or []
    for e in ruw[:MAX_EVENTS]:
        se, reden = schoon_event(e)
        if se and se["v"] not in venues:
            se, reden = None, "onbekend podium"
        if se:
            events.append(se)
        else:
            redenen[reden] += 1
    redenen["te veel items"] += max(0, len(ruw) - MAX_EVENTS)
    gebruikt = {e["v"] for e in events}
    return ({"updated": out.get("updated"), "venues": {k: v for k, v in venues.items() if k in gebruikt}, "events": events},
            {"in": len(ruw), "weg": len(ruw) - len(events), "redenen": +redenen})


def vangnet(status, skey, prev_n, n, today, min_items=6, max_dagen=7):
    """Vangnet bij stille uitval van één bron. prev_n = items van deze bron in de vorige data.json, n = items nu.
    Had de bron vorige keer minstens min_items en geeft hij nu niets (of bij >= 20 minder dan een kwart), dan zijn de oude
    items nog max_dagen dagen te zien; daarna vallen ze weg (de bron is dan echt leeg of weg).
    Geeft 'ok' (gezond, status bijgewerkt), 'houd' (oude items aanhouden) of 'vervallen' (te lang leeg, nu loslaten)."""
    kapot = prev_n >= min_items and (n == 0 or (prev_n >= 20 and n < prev_n * 0.25))
    if not kapot:
        status[skey] = {"ok": today.isoformat(), "n": n}
        return "ok"
    st = status.setdefault(skey, {"ok": today.isoformat(), "n": prev_n})
    try:
        dagen = (today - dt.date.fromisoformat(st["ok"])).days
    except (KeyError, ValueError, TypeError):
        st["ok"], dagen = today.isoformat(), 0
    return "houd" if dagen < max_dagen else "vervallen"
