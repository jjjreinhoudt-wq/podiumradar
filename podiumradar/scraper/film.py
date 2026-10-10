"""Draaitijden van bioscopen en filmhuizen, per kaartverkoopsysteem één uitlezer.

Een bron in bronnen.json met "type": "film" en "platform": "<naam>" gaat naar de uitlezer hieronder;
zonder (bekend) platform leest sources.py de site gewoon uit (JSON-LD ScreeningEvent of de filmpagina's).
Elke uitlezer geeft een lijst events: {"date", "time", "title", "url", optioneel "dur" (minuten)}.
"""
import datetime as dt, json, re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

NL = ZoneInfo("Europe/Amsterdam")
TODAY = dt.date.today()


def _days(cfg):
    return [TODAY + dt.timedelta(days=i) for i in range(cfg.get("film_days_ahead", 10))]


def _ev(d, t, title, url, dur=None):
    ev = {"date": d if isinstance(d, str) else d.isoformat(), "time": t, "title": title.strip(), "url": url}
    if dur:
        ev["dur"] = int(dur)
    return ev


def pathe(src, F, cfg, log):
    """pathe.nl/api: per bioscoop de films en dagen, daarna per film en dag de tijden."""
    slug = src["agenda_url"].rstrip("/").split("/")[-1]
    base = "https://www.pathe.nl/api"
    data = F.get_json(f"{base}/cinema/{slug}/shows")
    if not isinstance(data, dict):
        # Uitleg in het logboek (en via lokaal.py in lokaal.json): zo is van afstand te zien wat Pathé antwoordde
        log(f"  {src['name']}: geen lijst van Pathé (antwoorden: {F.stats.get('pathe.nl', {})}, gekregen: {type(data).__name__})")
        return []
    days = {d.isoformat() for d in _days(cfg)}
    shows = data.get("shows")
    if not isinstance(shows, dict) or not shows:
        log(f"  {src['name']}: Pathé-lijst zonder 'shows' (sleutels: {list(data)[:8]})")
        return []
    if not any(d in days for info in shows.values() if isinstance(info, dict) for d in (info.get("days") or {})):
        voorbeeld = next(iter(shows.items()))
        log(f"  {src['name']}: {len(shows)} films, maar geen speeldag in de komende dagen (voorbeeld: {str(voorbeeld)[:300]})")
    out, gezien = [], []
    for show, info in shows.items():
        if not isinstance(info, dict):
            continue
        want = sorted(d for d in (info.get("days") or {}) if d in days)
        if not want:
            continue
        meta = F.get_json(f"{base}/show/{show}") or {}
        title = meta.get("title") or show.rsplit("-", 1)[0].replace("-", " ").title()
        url = f"https://www.pathe.nl/nl/films/{show}"
        for d in want:
            times = F.get_json(f"{base}/show/{show}/showtimes/{slug}/{d}") or []
            if not isinstance(times, list):
                log(f"  {src['name']}: onverwachte draaitijden voor {show} op {d}: {str(times)[:200]}")
                continue
            for st in times:
                if not isinstance(st, dict):
                    continue
                gezien.append(st)
                m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", str(st.get("time", "")))
                if not m:
                    continue
                dur = None
                e = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}):(\d{2})", st.get("endTime") or "")
                if e:
                    h, mi = map(int, m.group(2).split(":"))
                    dur = (int(e.group(1)) * 60 + int(e.group(2)) - h * 60 - mi) % 1440 or None
                ev = _ev(m.group(1), m.group(2), title, url, dur)
                if st.get("status") in ("full", "soldout", "sold_out"):
                    ev["status"] = "sold"
                out.append(ev)
    if gezien and not out:  # wel draaitijden, maar in een vorm die we niet (meer) herkennen
        log(f"  {src['name']}: draaitijden niet herkend (voorbeeld: {str(gezien[0])[:300]})")
    return out


def cinecitta(src, F, cfg, log):
    """Cinecitta Tilburg: eigen REST-API voor voorstellingen, WordPress voor de filmtitels."""
    base = "{0.scheme}://{0.netloc}".format(urlparse(src["agenda_url"]))
    titles, links = {}, {}
    for m in F.get_json(f"{base}/wp-json/wp/v2/movie?movie_status=currently_playing&with_shows=true&type=") or []:
        sid = str((m.get("acf") or {}).get("movie_sync_id") or m.get("movie_sync_id") or "")
        if not sid:
            s = re.search(r'"movie_sync_id":\s*"?(\d+)', str(m).replace("'", '"'))
            sid = s.group(1) if s else ""
        if sid:
            titles[sid] = re.sub(r"<[^>]+>", "", (m.get("title") or {}).get("rendered", ""))
            links[sid] = m.get("link") or src["agenda_url"]
    out = []
    for d in _days(cfg):
        for s in F.get_json(f"{base}/rest-api/v1/wordpress-integration/shows/?movie_status=currently_playing&day={d}") or []:
            sid = str(s.get("movie_sync_id") or "")
            if sid not in titles:
                continue
            t0, t1 = s.get("start", ""), s.get("end", "")
            dur = None
            if len(t0) >= 16 and len(t1) >= 16:
                dur = ((int(t1[11:13]) * 60 + int(t1[14:16])) - (int(t0[11:13]) * 60 + int(t0[14:16]))) % 1440 or None
            out.append(_ev(s.get("day") or t0[:10], s.get("start_time") or t0[11:16], titles[sid], links[sid], dur))
    return out


def tribe(src, F, cfg, log):
    """WordPress 'The Events Calendar' (wp-json/tribe/events/v1)."""
    base = "{0.scheme}://{0.netloc}".format(urlparse(src["agenda_url"]))
    end = (TODAY + dt.timedelta(days=cfg.get("film_days_ahead", 10))).isoformat()
    out, page = [], 1
    while page <= 10:
        js = F.get_json(f"{base}/wp-json/tribe/events/v1/events?per_page=50&page={page}&start_date={TODAY}&end_date={end}")
        if not js or not js.get("events"):
            break
        for e in js["events"]:
            sd = e.get("start_date", "")
            title = re.sub(r"<[^>]+>", "", e.get("title", ""))
            # "aanvang film19:30: The Odyssey" -> "The Odyssey"
            title = re.sub(r"^\s*(aanvang|start)\s*(film)?\s*\d{1,2}[:.]\d{2}\s*[:\-]\s*", "", title, flags=re.I)
            t = sd[11:16] if len(sd) >= 16 and sd[11:16] != "00:00" else None
            out.append(_ev(sd[:10], t, title, e.get("url") or src["agenda_url"]))
        if page >= int(js.get("total_pages") or 1):
            break
        page += 1
    return out


def ticketlab(src, F, cfg, log):
    """Ticketlab: tickets.<domein>/agenda.php met rijen 'Wed Sep 30' / '1:30 pm' / titel."""
    host = urlparse(src["agenda_url"]).netloc.removeprefix("www.")
    url = src.get("api_url") or f"https://tickets.{host}/agenda.php"
    html = F.get(url)
    if not html:
        return []
    # Nederlands ("wo 30 sep", "13:30") of Engels ("Wed Sep 30", "1:30 pm"), afhankelijk van de taal
    mon = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
    mon.update({"mrt": 3, "mei": 5, "okt": 10})
    out = []
    for row in BeautifulSoup(html, "html.parser").select("div.row-with-show"):
        d = row.select_one(".agenda-show-date")
        t = row.select_one(".agenda-show-time")
        a = row.select_one(".agenda-show-event a")
        if not (d and t and a):
            continue
        ds = d.get_text(" ", strip=True).lower()
        md = re.search(r"(\d{1,2})\s+([a-z]{3})", ds) or re.search(r"([a-z]{3})\s+(\d{1,2})\b(?!:)", ds.split(" ", 1)[-1])
        mt = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m)?", t.get_text(" ", strip=True), re.I)
        if not md or not mt:
            continue
        day_s, mon_s = (md.group(1), md.group(2)) if md.group(1).isdigit() else (md.group(2), md.group(1))
        if mon_s not in mon:
            continue
        m, day = mon[mon_s], int(day_s)
        y = TODAY.year + (1 if m < TODAY.month - 1 else 0)
        h = int(mt.group(1)) % 12 + (12 if (mt.group(3) or "").lower() == "pm" else 0) if mt.group(3) else int(mt.group(1))
        out.append(_ev(dt.date(y, m, day), f"{h:02d}:{mt.group(2)}", a.get_text(" ", strip=True), urljoin(url, a["href"])))
    return out


def cinelink(src, F, cfg, log):
    """Cinelink: /film-overzicht/agenda-per-dag, per film een rij met tijden (data-timestamp)."""
    html = F.get(src["agenda_url"])
    if not html:
        return []
    out = []
    for row in BeautifulSoup(html, "html.parser").select("div.movierow"):
        a = row.select_one(".movieinfo a")
        title = (a.get_text(" ", strip=True) if a else "") or row.get("data-name", "").title()
        url = urljoin(src["agenda_url"], a["href"]) if a and a.get("href") else src["agenda_url"]
        for tm in row.select("a.time[data-timestamp]"):
            try:
                x = dt.datetime.fromtimestamp(int(tm["data-timestamp"]), NL)
            except (ValueError, OverflowError):
                continue
            out.append(_ev(x.date(), x.strftime("%H:%M"), title, url))
    return out


def wpgraphql(src, F, cfg, log):
    """Eagerly headless (Focus Arnhem, Lumière): backend.<domein>/wp/graphql."""
    host = urlparse(src["agenda_url"]).netloc.removeprefix("www.")
    q = "{movies(first:200){nodes{title link performances{startAt facility}}}}"
    js = F.get_json(f"https://backend.{host}/wp/graphql", params={"query": q}) or {}
    out, seen = [], set()
    for m in ((js.get("data") or {}).get("movies") or {}).get("nodes") or []:
        if "/en/" in (m.get("link") or ""):
            continue  # Engelse kopie van dezelfde film
        for p in m.get("performances") or []:
            s = re.sub(r"\D", "", p.get("startAt") or "")  # "202609301800" of "2026-10-03 10:45:00"
            if len(s) < 12:
                continue
            key = (m["title"], s[:12])
            if key in seen:
                continue
            seen.add(key)
            out.append(_ev(f"{s[:4]}-{s[4:6]}-{s[6:8]}", f"{s[8:10]}:{s[10:12]}", m["title"], m.get("link") or src["agenda_url"]))
    return out


def fraterhuis(src, F, cfg, log):
    js = F.get_json("https://api.filmtheaterfraterhuis.nl/api/events/shows") or []
    out = []
    for s in js:
        data = ((s.get("event") or {}).get("data") or {})
        m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", s.get("datetime", ""))
        if m and data.get("title"):
            out.append(_ev(m.group(1), m.group(2), data["title"], src["agenda_url"], data.get("featurelength")))
    return out



def _astro(v):
    """Astro-props: elke waarde is [type, waarde]; 1 = lijst, 3 = datum, 0 = gewoon of object."""
    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int):
        t, x = v
        if t == 1 and isinstance(x, list):
            return [_astro(i) for i in x]
        return _astro(x) if isinstance(x, dict) else x
    if isinstance(v, dict):
        return {k: _astro(i) for k, i in v.items()}
    return v


def _productions(x):
    """Alle producties (dicts met een lijst 'screenings'), waar ze ook staan in de props."""
    if isinstance(x, dict):
        if isinstance(x.get("screenings"), list):
            yield x
        for v in x.values():
            yield from _productions(v)
    elif isinstance(x, list):
        for v in x:
            yield from _productions(v)


def tricket(src, F, cfg, log):
    """Tricket op een Astro-site (Cinecenter): films en voorstellingen staan in de props van <astro-island> op /films/
    ('productions' naast 'data'; we zoeken ze overal, zodat een verschuiving in de opbouw niet meteen alles breekt)."""
    html = F.get(src["agenda_url"])
    if not html:
        return []
    out, seen = [], set()
    for isl in BeautifulSoup(html, "html.parser").find_all("astro-island", props=True):
        try:
            p = _astro(json.loads(isl["props"]))
        except ValueError:
            continue
        for prod in _productions(p):
            for sc in prod["screenings"]:
                if not isinstance(sc, dict) or not isinstance(sc.get("startAtUtc"), str) or (sc.get("id"), sc["startAtUtc"]) in seen:
                    continue
                seen.add((sc.get("id"), sc["startAtUtc"]))
                try:
                    x = dt.datetime.fromisoformat(sc["startAtUtc"].replace("Z", "+00:00")).astimezone(NL)
                except ValueError:
                    continue
                dur = prod.get("durationInMinutes")
                out.append(_ev(x.date(), x.strftime("%H:%M"), str(prod.get("title") or ""), sc.get("url") or src["agenda_url"],
                               dur if isinstance(dur, int) else None))
    return [e for e in out if e["title"]]


PLATFORMS = {"pathe": pathe, "cinecitta": cinecitta, "tribe": tribe, "ticketlab": ticketlab,
             "cinelink": cinelink, "wpgraphql": wpgraphql, "fraterhuis": fraterhuis, "tricket": tricket}


def scrape(src, F, cfg, log):
    fn = PLATFORMS[src["platform"]]
    last = (TODAY + dt.timedelta(days=cfg.get("film_days_ahead", 10))).isoformat()
    evs = [e for e in fn(src, F, cfg, log) if TODAY.isoformat() <= e["date"] < last]
    log(f"  {src['name']}: {len(evs)} voorstellingen ({src['platform']})")
    return evs
