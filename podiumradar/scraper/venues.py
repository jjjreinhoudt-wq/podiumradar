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


def _dt(s):
    """'2026-10-02T20:15:00+02:00' of '2026-10-02T20:15:00' -> (datum, tijd), kloktijd zoals de site hem geeft."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", s or "")
    return (m.group(1), m.group(2) if m.group(2) != "00:00" else None) if m else (None, None)


def _site(src):
    m = re.match(r"https?://[^/]+", src["agenda_url"])
    return m.group(0)


def cre8ion(src, F, cfg, log):
    """cre8ion IDPS (Het Zuidelijk Toneel, De Cammeleur, 't Voorhuys): POST {api_base}/nl/api/events.
    location_filter: alleen voorstellingen in deze plaats (HZT reist het land rond)."""
    out, page, site = [], 1, _site(src)
    while page <= 20:
        js = F.post_json(src["api_base"].rstrip("/") + "/nl/api/events",
                         {"filters": {"startAt": f"{TODAY}T00:00:00.000Z", "searchTerm": ""},
                          "pagination": {"page": page, "pageSize": 100}, "sortings": []}) or {}
        for e in js.get("events") or []:
            for p in e.get("programs") or []:
                if p.get("isCanceled"):
                    continue
                loc = (p.get("location") or {}).get("name") or ""
                if src.get("location_filter") and src["location_filter"].lower() not in loc.lower():
                    continue
                d, t = _dt(p.get("startAt"))
                if d:
                    out.append({"date": d, "time": t, "title": e.get("title", ""), "url": site + (e.get("url") or "")})
        if page >= int((js.get("pagination") or {}).get("pages") or 1):
            break
        page += 1
    return out


def render_api(src, F, cfg, log):
    """Carré / De Rijswijkse Schouwburg: /api/render/production-page-list-nl (alles in één antwoord)."""
    site = _site(src)
    js = F.get_json(src.get("api_url") or site + "/api/render/production-page-list-nl") or {}
    prods = js.get("productions") or {}
    out = []
    for node in (js.get("nodes") or {}).values():
        if node.get("kind") != "production-page":
            continue
        data = node.get("data") or {}
        for e in (prods.get(str(node.get("production_id"))) or {}).get("events") or []:
            d, t = _dt(e.get("start_date"))
            if not d:
                continue
            ev = {"date": d, "time": t, "title": data.get("title", ""), "url": site + (data.get("url") or "")}
            if "sold" in str(e.get("sales_status", "")).lower():
                ev["status"] = "sold"
            out.append(ev)
    return out


def umbraco_agenda(src, F, cfg, log):
    """Umbraco 'AgendaItems' (De Vest, De Purmaryn): POST met Limit/Offset; api_url en api_body in bronnen.json."""
    site, out, offset = _site(src), [], 0
    while offset < 3000:
        body = dict(src.get("api_body") or {}, Limit=200, Offset=offset)
        js = F.post_json(src["api_url"], body) or {}
        items = js.get("items") or []
        for e in items:
            if e.get("isExhibit"):
                continue
            d, t = _dt(e.get("start") or e.get("startDate"))
            title = (e.get("title") or "").strip()
            if e.get("performer") and e["performer"].strip().lower() not in title.lower():
                title = f"{e['performer'].strip()} - {title}"
            url = e.get("detailUrl") or e.get("agendaItemUrl") or ""
            if d and title:
                out.append({"date": d, "time": t, "title": title, "url": url if url.startswith("http") else site + url})
        offset += 200
        if not items or offset >= int(js.get("totalCount") or js.get("queryCount") or 0):
            break
    return out


def umbraco_getshows(src, F, cfg, log):
    """Umbraco + Yesplan 'Search/GetShows' (Zaantheater)."""
    site = _site(src)
    js = F.get_json(site + "/umbraco/api/Search/GetShows", {"lang": "nl", "productiontypes": "theatre", "limit": 500}) or {}
    out = []
    for e in js.get("Data") or []:
        p = e.get("Production") or {}
        d, t = _dt(e.get("Start"))
        if d and p.get("Title"):
            out.append({"date": d, "time": t, "title": p["Title"].strip(), "url": site + (p.get("Url") or "")})
    return out


def itix(src, F, cfg, log):
    """Itix CMS (Ogterop, Hof 88, Zeelandtheaters, Maaspoort): /shows.php?page=N geeft JSON met html.
    Datum en tijd staan ook in de link: /programma/<slug>/01-10-2026-20-15."""
    site, out, page = _site(src), [], 1
    while page <= 40:
        js = F.get_json(site + "/shows.php", {"page": page, "genres": "", "dates": "", "type": src.get("itix_type", "theatre")}) or {}
        soup = BeautifulSoup(js.get("html") or "", "html.parser")
        for art in soup.select("article.program-block"):
            ttl = art.select_one(".program-block__title")
            sub = art.select_one(".program-block__subtitle")
            link = art.select_one("a.icon-info[href]") or art.select_one("a[href*='/programma/']")
            href = link["href"] if link else ""
            if not href:
                m = re.search(r"location\s*=\s*'([^']+)'", str(art))
                href = m.group(1) if m else ""
            m = re.search(r"/(\d{2})-(\d{2})-(\d{4})-(\d{2})-(\d{2})/?$", href)
            if not (ttl and m):
                continue
            title = ttl.get_text(" ", strip=True)
            if sub and sub.get_text(strip=True):
                title = f"{title} - {sub.get_text(' ', strip=True)}"
            ev = {"date": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "time": f"{m.group(4)}:{m.group(5)}",
                  "title": title, "url": href if href.startswith("http") else site + href}
            lab = art.select_one(".program-block__label")
            if lab and "uitverkocht" in lab.get_text().lower():
                ev["status"] = "sold"
            out.append(ev)
        if page >= int(js.get("pages") or 1):
            break
        page += 1
    return out


PLATFORMS = {"ziggodome": ziggodome, "melkweg": melkweg, "tolhuistuin": tolhuistuin, "musis": musis,
             "cre8ion": cre8ion, "render_api": render_api, "umbraco_agenda": umbraco_agenda,
             "umbraco_getshows": umbraco_getshows, "itix": itix}


def scrape(src, F, cfg, log):
    evs = [e for e in PLATFORMS[src["platform"]](src, F, cfg, log) if e["date"] >= TODAY.isoformat()]
    log(f"  {src['name']}: {len(evs)} items ({src['platform']})")
    return evs
