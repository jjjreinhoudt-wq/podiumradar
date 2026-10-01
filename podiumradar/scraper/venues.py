"""Eigen uitlezers voor losse podia/theaters die hun agenda alleen via een eigen API of ingebedde JSON tonen.

Een bron in bronnen.json met "platform": "<naam>" (zie PLATFORMS) gaat hierheen.
Elke uitlezer geeft events {"date", "time", "title", "url", optioneel "doors", "status", "support"}.
"""
import datetime as dt, json, re
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

NL = ZoneInfo("Europe/Amsterdam")
TODAY = dt.date.today()


def _local(iso):
    """ISO-tijd met tijdzone (of Z) -> (datum, 'HH:MM') in Nederlandse tijd."""
    t = dt.datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))
    if t.tzinfo:
        t = t.astimezone(NL)
    return t.date().isoformat(), t.strftime("%H:%M")


def ziggodome(src, F, cfg, log):
    """Ziggo Dome: /api/agenda/aankomend/ (de tijd is vrijwel altijd 'deuren open')."""
    out, offset = [], 0
    while offset < 1000:
        js = F.get_json(f"https://www.ziggodome.nl/api/agenda/aankomend/?limit=50&offset={offset}") or {}
        for e in js.get("data") or []:
            m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", e.get("showDate") or "")
            if not m or e.get("privateEvent"):
                continue
            ev = {"date": m.group(1), "time": m.group(2), "title": e.get("performerName") or (e.get("event") or {}).get("title", ""),
                  "url": f"https://www.ziggodome.nl/events/{e.get('eventId')}"}
            if not e.get("showShowTime"):
                ev["doors"] = m.group(2)  # site toont geen aanvang: dit is deuren open
            if e.get("showState") == "SoldOut":
                ev["status"] = "sold"
            out.append(ev)
        if not (js.get("pagination") or {}).get("hasMore"):
            break
        offset += 50
    return out


def melkweg(src, F, cfg, log):
    """Melkweg: __NEXT_DATA__ op de agendapagina, startDate in UTC (= deuren open)."""
    html = F.get(src["agenda_url"])
    if not html:
        return []
    tag = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    try:
        content = json.loads(tag.string)["props"]["pageProps"]["pageData"]["attributes"]["content"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return []
    events = next((c["attributes"]["initialEvents"] for c in content if "initialEvents" in (c.get("attributes") or {})), [])
    out = []
    for e in events:
        a = e.get("attributes") or e
        if not a.get("startDate") or a.get("isCancelled"):
            continue
        d, t = _local(a["startDate"])
        ev = {"date": d, "time": t, "doors": t, "title": a.get("name", ""), "url": "https://www.melkweg.nl" + (a.get("url") or "")}
        if a.get("isSoldOut"):
            ev["status"] = "sold"
        out.append(ev)
    return out


def tolhuistuin(src, F, cfg, log):
    """Tolhuistuin: JSON in het attribuut ':all-items' van <agenda-filter-component>."""
    html = F.get(src["agenda_url"])
    comp = BeautifulSoup(html or "", "html.parser").find("agenda-filter-component")
    try:
        items = json.loads(comp[":all-items"])
    except (TypeError, KeyError, ValueError):
        return []
    out = []
    for e in items:
        m = re.match(r"(\d{4})/(\d{2})/(\d{2}) (\d{2}:\d{2})", e.get("eventStartDate") or "")
        if not m:
            continue
        ev = {"date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "time": m.group(4) if m.group(4) != "00:00" else None,
              "title": e.get("title", ""), "url": e.get("url") or src["agenda_url"]}
        if e.get("soldOut"):
            ev["status"] = "sold"
        out.append(ev)
    return out


def musis(src, F, cfg, log):
    """Musis & Stadstheater Arnhem: API Platform /api/events (10 per pagina)."""
    out, page = [], 1
    while page <= 80:
        js = F.get_json("https://www.musisenstadstheater.nl/api/events", {"page": page, "startsAt[after]": TODAY.isoformat()}) or {}
        for e in js.get("member") or js.get("hydra:member") or []:
            p = e.get("production") or {}
            if not e.get("startsAt") or not p.get("title"):
                continue
            d, t = _local(e["startsAt"])
            ev = {"date": d, "time": t, "title": p["title"],
                  "url": f"https://www.musisenstadstheater.nl/nl/agenda/{p.get('slug', '')}/{e.get('id', '')}"}
            if p.get("performer") and p["performer"].lower() not in p["title"].lower():
                ev["title"] = f"{p['performer']} - {p['title']}"
            if e.get("soldOut"):
                ev["status"] = "sold"
            out.append(ev)
        view = js.get("view") or js.get("hydra:view") or {}
        if not (view.get("next") or view.get("hydra:next")):
            break
        page += 1
    return out


PLATFORMS = {"ziggodome": ziggodome, "melkweg": melkweg, "tolhuistuin": tolhuistuin, "musis": musis}


def scrape(src, F, cfg, log):
    evs = [e for e in PLATFORMS[src["platform"]](src, F, cfg, log) if e["date"] >= TODAY.isoformat()]
    log(f"  {src['name']}: {len(evs)} items ({src['platform']})")
    return evs
