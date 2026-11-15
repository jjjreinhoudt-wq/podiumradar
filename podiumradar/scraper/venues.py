"""Eigen uitlezers voor losse podia/theaters die hun agenda alleen via een eigen API of ingebedde JSON tonen.

Een bron in bronnen.json met "platform": "<naam>" (zie PLATFORMS) gaat hierheen.
Elke uitlezer geeft events {"date", "time", "title", "url", optioneel "doors", "status", "support"}.
"""
import datetime as dt, json, re, time
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from html import unescape
from urllib.parse import urljoin
import prijzen

NL = ZoneInfo("Europe/Amsterdam")
TODAY = dt.date.today()


def _local(iso):
    """ISO-tijd met tijdzone (of Z) -> (datum, 'HH:MM') in Nederlandse tijd."""
    t = dt.datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))
    if t.tzinfo:
        t = t.astimezone(NL)
    return t.date().isoformat(), t.strftime("%H:%M")


HHMM = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
DOORS_RE = re.compile(r"deur|doors|zaal\s*open|^open$|opening", re.I)
SKIP_RE = re.compile(r"eind|einde|\bend\b|curfew|sluit|close|pauze|break|aanvang|^start$|begin|kassa|garderobe|"
                     r"\bvip\b|meet ?(&|and|n) ?greet|\bm&g\b|soundcheck|merch|"
                     r"^(intro|introductie|inleiding|q ?& ?a|nagesprek|aftertalk|film|filmscreening|screening|"
                     r"workshop|lezing|talk|borrel|programma|pre-?party|after-?party|live-?concert|concert|show|"
                     r"voorprogramma|support|hoofdact|headliner)$", re.I)
# Regel uit een tijdschema: '19:15 uur: CJ's Mirra Maze', '19:00 Doors', '13:00 - 14:30: filmscreening'
LINE_RE = re.compile(r"^\s*(\d{1,2}[:.]\d{2})(?:\s*[-–]\s*\d{1,2}[:.]\d{2})?\s*(?:uur)?\s*[:\-–]?\s+(\S.*)$")


NO_ACT_RE = re.compile(r"^\s*(geen|none|no support|tba|tbc|n\.?n\.?b|nog niet bekend|volgt|onbekend)\b|wordt .{0,20}bekend|bekend ?gemaakt|announced", re.I)


def _norm(s):
    """Naam om te vergelijken: 'Rob Lamberti [part 1]' -> 'roblamberti'."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\[[^\]]*\]|\([^)]*\)", "", (s or "").lower()))


def split_acts(s):
    """'Alison's Halo, CJ's Mirra Maze' / 'X & Y' / 'X + Y' -> namen."""
    if NO_ACT_RE.search(s or ""):
        return []
    return [x.strip() for x in re.split(r",|&| en | \+ | and ", s or "") if _norm(x)]


def schedule(rows, title):
    """Tijdschema van het podium [('19:00', 'Deuren open'), ('19:30', 'Ben Caplan'), ('20:30', 'Yaelokre')] ->
    {"doors", "start", "support", "times"}. Alleen wat er echt staat: deuren open, en per act de begintijd.
    De hoofdact is de act met (een deel van) de titel als naam (start = begin hoofdact, support = de acts ervoor);
    heet geen act zo, dan alleen de tijden."""
    out, acts = {}, []
    for t, label in rows:
        m = HHMM.search(t or "")
        label = " ".join((label or "").split()).strip(" :-–")
        if not m or not label:
            continue
        t = f"{int(m.group(1)):02d}:{m.group(2)}"
        if re.search(r"\bvip\b|meet ?(&|and|n) ?greet|\bm&g\b|early entry", label, re.I):
            continue  # deuren/programma voor VIP-kaarten, niet voor iedereen
        if DOORS_RE.search(label):
            out.setdefault("doors", t)
        elif not SKIP_RE.search(label) and len(label) <= 80:
            acts.append({"a": label, "s": t})
    if not acts:
        return out
    key = _norm(title)
    main = next((i for i, x in enumerate(acts) if _norm(x["a"]) and (_norm(x["a"]) in key or key in _norm(x["a"]))), None)
    # Na middernacht (00:30) telt door; de lijst moet oplopen, anders vertrouwen we hem niet
    mins = [int(x["s"][:2]) * 60 + int(x["s"][3:]) for x in acts]
    mins = [m + 1440 if m < mins[0] - 360 else m for m in mins]
    if mins != sorted(mins) or len(acts) > 15:
        return out
    out["times"] = acts
    if main is None:  # geen act heet zoals de voorstelling (clubnacht, festival): geen hoofdact/voorprogramma raden
        return out
    out["start"] = acts[main]["s"]
    sup = [x["a"] for i, x in enumerate(acts) if i < main]
    if sup:
        out["support"] = sup[:6]
    return out


def detail_times(soup, title):
    """Settijden van een voorstellingspagina (bronnen.json "timetable": true), herkent:
    - 013: <li><b><time>18:30</time> - <time>19:00</time></b><div>Orthodox</div></li> (eerste regel 'Zaal Open')
    - TivoliVredenburg: <dl class="description-list"> met tijd + 'Deuren open' / 'Aanvang' en 'Support act'
    - tekstregels '19:15 uur: CJ's Mirra Maze' / '19:00 Doors'."""
    for ul in soup.find_all("ul"):
        rows = []
        for li in ul.find_all("li", recursive=False):
            b, lab = li.find("b"), li.find("div")
            tm = b.find("time") if b else None
            if tm and lab:
                rows.append((tm.get_text(" ", strip=True), lab.get_text(" ", strip=True)))
        if len(rows) >= 2:
            return schedule(rows, title)
    dl = soup.select_one("dl.description-list")
    if dl:
        out, rows, no_support = {}, [], True
        for dt_ in dl.find_all("dt"):
            label = dt_.get_text(" ", strip=True)
            if "--group" in " ".join(dt_.get("class", [])):
                dd = dt_.find_previous_sibling("dd")  # bij Tivoli staat de tijd vóór het label
                if dd and dd.find("time"):
                    rows.append((dd.find("time").get_text(strip=True), label))
            elif re.match(r"support", label, re.I):
                dd = dt_.find_next_sibling("dd")
                txt = " , ".join(dd.stripped_strings) if dd else ""
                sup = split_acts(txt)
                no_support = not sup and bool(re.match(r"\s*geen", txt, re.I))  # 'Geen voorprogramma'; 'TBA' = onbekend
                if sup or no_support:
                    out["support"] = sup[:6]  # [] bij 'Geen voorprogramma': ook geen namen uit de JSON-LD
        for t, label in rows:
            if DOORS_RE.search(label):
                out["doors"] = t
            elif re.match(r"aanvang|start", label, re.I) and no_support:
                out["start"] = t  # zonder voorprogramma is de aanvang de hoofdact; met voorprogramma weten we het niet
        return out
    rows = [m.groups() for x in soup.get_text("\n", strip=True).split("\n") if (m := LINE_RE.match(x))]
    return schedule(rows, title) if len(rows) >= 2 else {}


def ziggodome(src, F, cfg, log):
    """Ziggo Dome: /api/agenda/aankomend/ (de tijd is vrijwel altijd 'deuren open'), 50 per pagina.
    Sinds eind okt 2026 staat Cloudflare ervoor: de eerste pagina komt vaak uit de cache, een volgende krijgt soms 403.
    Dan wachten we even en proberen we die pagina nog twee keer; lukt het dan nog niet, dan geven we een fout
    (en geen halve lijst, want dan zouden de shows van over twee maanden uit de agenda verdwijnen)."""
    out, offset = [], 0
    while offset < 1000:
        url = f"https://www.ziggodome.nl/api/agenda/aankomend/?limit=50&offset={offset}"
        js = F.get_json(url)
        for poging in range(2):
            if isinstance(js, dict):
                break
            log(f"  {src['name']}: pagina met offset {offset} niet gekregen (antwoorden: {F.stats.get('ziggodome.nl', {})}); even wachten en opnieuw")
            time.sleep(20 * (poging + 1))
            js = F.get_json(url)
        if not isinstance(js, dict):
            raise RuntimeError(f"Ziggo Dome weigert pagina met offset {offset} (antwoorden: {F.stats.get('ziggodome.nl', {})})")
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
    # Settijden ('19:00 Doors / 19:30 Ben Caplan / 20:30 Yaelokre') staan alleen op de voorstellingspagina:
    # die halen we voor de komende dagen (timetable_days, standaard 14), één verzoek per voorstelling.
    until = (TODAY + dt.timedelta(days=src.get("timetable_days", 14))).isoformat()
    for ev in out:
        if not (TODAY.isoformat() <= ev["date"] <= until):
            continue
        tag = BeautifulSoup(F.get(ev["url"]) or "", "html.parser").find("script", id="__NEXT_DATA__")
        try:
            meta = json.loads(tag.string)["props"]["pageProps"]["pageData"]["attributes"]["metadata"]
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        rows = [m.groups() for x in re.split(r"[\r\n]+", (meta or {}).get("timeschedule") or "")
                if (m := LINE_RE.match(x))]
        sch = schedule(rows, ev["title"])
        if re.search(r"\(\d{4}\)\s*$", ev["title"]):  # film ('Naked (1993)'): alleen deuren, geen 'acts'
            sch = {k: v for k, v in sch.items() if k == "doors"}
        ev.update(sch)
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
    Nieuwere sites (Maaspoort, okt 2026) geven daar alleen aantallen: dan de kaarten van /programma/?page=N zelf.
    Datum en tijd staan ook in de link: /programma/<slug>/01-10-2026-20-15."""
    site, out, page, ssr = _site(src), [], 1, False
    loc_rx = r"location(?:\.href)?\s*=\s*'([^']+)'"
    while page <= 40:
        js = {} if ssr else F.get_json(site + "/shows.php", {"page": page, "genres": "", "dates": "", "type": src.get("itix_type", "theatre")}) or {}
        html, pages = js.get("html"), int(js.get("pages") or 1)
        if not html:   # nieuwe opbouw: de programmapagina zelf (en dan shows.php niet meer vragen)
            ssr = True
            html = F.get(f"{site}/programma/?page={page}") or ""
            m = re.search(r'data-ssr-pages="(\d+)"', html)
            pages = int(m.group(1)) if m else pages
        soup = BeautifulSoup(html, "html.parser")
        for art in soup.select("article.program-block, div.program-block"):
            ttl = art.select_one(".program-block__title, .program-block-title .title")
            sub = art.select_one(".program-block__subtitle, .program-block-title .subtitle")
            m = re.search(loc_rx, art.get("onclick") or "")
            link = art.select_one("a.icon-info[href]") or art.select_one("a[href*='/programma/'][href$='/']")
            href = m.group(1) if m else (link["href"] if link else "")
            if not re.search(r"/\d{2}-\d{2}-\d{4}-\d{2}-\d{2}/?$", href):
                m = re.search(loc_rx, str(art))
                href = m.group(1) if m else href
            m = re.search(r"/(\d{2})-(\d{2})-(\d{4})-(\d{2})-(\d{2})/?$", href)
            if not (ttl and m):
                continue
            title = ttl.get_text(" ", strip=True)
            if sub and sub.get_text(strip=True):
                title = f"{title} - {sub.get_text(' ', strip=True)}"
            ev = {"date": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "time": f"{m.group(4)}:{m.group(5)}",
                  "title": title, "url": href if href.startswith("http") else site + href}
            lab = art.select_one(".program-block__label, .program-block-label")
            if (lab and "uitverkocht" in lab.get_text().lower()) or art.select_one("[data-status='uitverkocht']"):
                ev["status"] = "sold"
            out.append(ev)
        if page >= pages or not html:
            break
        page += 1
    return out


PARADISO_Q = ("query($site:String,$size:Int,$gteStartDateTime:String,$searchAfter:[String]){program(site:$site,size:$size,"
              "gteStartDateTime:$gteStartDateTime,searchAfter:$searchAfter){events{id uri title subtitle startDateTime "
              "sort eventStatus supportAct soldOut location{title}}}}")
# Met tijden (deuren open, begin voorprogramma, begin hoofdact); kent de dienst die velden niet meer, dan zonder
PARADISO_QT = PARADISO_Q.replace("supportAct ", "supportAct doorsOpen startMain startSupportAct ")


def paradiso_api(site, F):
    """Adres en openbare sleutel van de programma-dienst, uit de eigen JavaScript van paradiso.nl."""
    html = F.get(site + "/") or ""
    for chunk in sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', html)), key=lambda c: "execute" not in c):
        js = F.get_text(site + chunk) or ""
        if "execute-api" not in js:
            continue
        m = re.search(r'"(https://[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com)"\s*,\s*"(/graphql)"', js)
        k = re.search(r'"Bearer "\.concat\("([A-Za-z0-9_\-]+)"\)|Bearer ([A-Za-z0-9_\-]{20,})', js)
        if m and k:
            return m.group(1) + m.group(2), k.group(1) or k.group(2)
    return None, None


def paradiso(src, F, cfg, log):
    """Paradiso: de site haalt zijn programma bij een GraphQL-dienst met een openbare sleutel die in de eigen
    JavaScript van paradiso.nl staat. We lezen adres en sleutel elke run opnieuw uit die JavaScript (niets vast
    in de code), en doen daarna dezelfde aanvraag als de site. Met toestemming van de eigenaar (okt 2026).
    location: alleen voorstellingen op deze locatie (de dienst geeft ook Tolhuistuin, Bitterzoet, ...)."""
    site = _site(src)
    endpoint, key = paradiso_api(site, F)
    if not endpoint:
        log(f"  {src['name']}: adres van het programma niet gevonden in de site")
        return []
    want = src.get("location", "Paradiso").lower()
    out, after, page, query = [], None, 0, PARADISO_QT
    while page < 20:
        var = {"site": "paradisoNederlands", "size": 100, "gteStartDateTime": f"{TODAY}T00:00:00.000Z"}
        if after:
            var["searchAfter"] = after
        js = F.post_json(endpoint, {"query": query, "variables": var}, headers={"Authorization": f"Bearer {key}"}) or {}
        if js.get("errors") and query is PARADISO_QT:
            log(f"  {src['name']}: tijden niet beschikbaar ({js['errors'][0].get('message', '')[:80]}), zonder tijden verder")
            query = PARADISO_Q
            continue
        evs = (((js.get("data") or {}).get("program") or {}).get("events")) or []
        if not evs:
            break
        for e in evs:
            locs = [(l or {}).get("title", "").lower() for l in (e.get("location") or [])]
            if want not in locs or e.get("eventStatus") in ("canceled", "cancelled"):
                continue
            d, t = _dt(e.get("startDateTime"))
            if not d:
                continue
            ev = {"date": d, "time": t, "title": (e.get("title") or "").strip(), "url": f"{site}/{e.get('uri', '')}"}
            if e.get("supportAct"):
                ev["support"] = [s.strip() for s in re.split(r",|&| en | \+ ", e["supportAct"]) if s.strip()][:3]
            # Tijden: 'startSupportAct' staat ook ingevuld (19:28) als er geen voorprogramma is: dan negeren.
            # Eén voorprogramma: echte settijden. Meer voorprogramma's: alleen deuren en hoofdact (volgorde onbekend).
            hm = lambda x: x if isinstance(x, str) and HHMM.fullmatch(x.strip()) and len(x.strip()) == 5 else None
            doors, main, sup = hm(e.get("doorsOpen")), hm(e.get("startMain")), hm(e.get("startSupportAct"))
            if doors and (not t or doors <= t) and doors != main:
                ev["doors"] = doors
            if main and (not t or main >= t):
                ev["start"] = main
                if len(ev.get("support", [])) == 1 and sup and (not doors or sup >= doors) and sup < main:
                    ev["times"] = [{"a": ev["support"][0], "s": sup}, {"a": ev["title"], "s": main}]
            if str(e.get("soldOut", "no")).startswith("yes"):
                ev["status"] = "sold"
            out.append(ev)
        after = evs[-1].get("sort")
        page += 1
    return out


_MON = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}


def _textdate(txt):
    """'wo 14 okt 26' / 'vr 9 okt 2026' / "do 8 okt '26" / 'do 8 okt' -> '2026-10-14' (terugval als
    data-event-start ontbreekt). Zonder jaartal: de eerstvolgende keer dat die datum valt."""
    m = re.search(r"\b(\d{1,2})\s+([a-z]{3})[a-z]*\.?(?:\s+['\u2019]?(\d{4}|\d{2})\b(?![:.]\d))?", txt or "", re.I)
    if not m or m.group(2).lower()[:3] not in _MON:
        return None
    y = (int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)) if m.group(3) else TODAY.year
    try:
        d = dt.date(y, _MON[m.group(2).lower()[:3]], int(m.group(1)))
    except ValueError:
        return None
    if not m.group(3) and d < TODAY - dt.timedelta(days=60):
        d = d.replace(year=y + 1)
    return d.isoformat()


def _peppered_price(el):
    """Prijsknop ('€ 35,50–€ 37,50') of het prijsvak zonder de uitklaptabel (daar staan ook servicekosten in)."""
    btn = el.select_one(".pricePopoverBtn")
    if btn:
        return btn.get_text(" ")
    box = el.select_one(".price")
    if not box:
        return ""
    box = BeautifulSoup(str(box), "html.parser")
    for x in box.select(".item-prices"):
        x.decompose()
    return box.get_text(" ")


def peppered(src, F, cfg, log):
    """Peppered-theatersites (Muziekgebouw, De Doelen, HNT, Kampanje, Orpheus, Wilminktheater, ...; kaartverkoop via
    Tixly/Itix, links als /agenda/<naam>-<4 tekens> en /order/add/event/<id>). Elke kaart op de agendapagina
    (li.eventCard) bevat al alle speeldata: per voorstelling een knop met data-event-start="2026-10-14 20:15:00" en
    een status (status-uitverkocht, ...). We lezen dus alleen de agendapagina's (?pNN_page=2, ...) en geen losse
    voorstellingspagina's: een paar dozijn verzoeken in plaats van honderden (de sites vragen 5 s pauze en staan
    samen op een server). Geen enkele kaart gevonden: None, dan gaat de bron via de gewone uitlezer."""
    site, url, pages, out, seen, cards = _site(src), src["agenda_url"], 0, [], set(), 0
    while url and pages < src.get("max_pages", 60):
        html = F.get(url) or F.get(url)  # een keer opnieuw proberen (de server is soms traag)
        pages += 1
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(".eventCard"):
            cards += 1
            link = card.select_one("a.desc[href]") or card.select_one("a[href]")
            ttl = card.select_one(".title")
            if not (link and ttl):
                continue
            title = ttl.get_text(" ", strip=True)
            href = link["href"] if link["href"].startswith("http") else site + link["href"]
            for unit in card.select("li.subshow") or [card]:
                starts = sorted({el["data-event-start"] for el in unit.select("[data-event-start]")})
                if not starts:  # geen knop met data-event-start (Muziekgebouw, Agora): datum en tijd uit de tekst
                    dd = unit.select_one(".date .start") or unit.select_one(".top-date .start") or unit.select_one(".date")
                    d = _textdate(dd.get_text(" ") if dd else "")
                    tm = unit.select_one(".time .start") or unit.select_one(".top-date .time")
                    tm = re.search(r"\d{1,2}:\d{2}", tm.get_text(" ") if tm else "")
                    starts = [f"{d} {tm.group(0) if tm else ''}"] if d else []
                st = " ".join(" ".join(el.get("class", [])) for el in unit.select("[class*=status-]")).lower()
                for s in starts:
                    m = re.match(r"(\d{4}-\d{2}-\d{2})\s*(\d{1,2}:\d{2})?", s)
                    if not m or (href, s) in seen:
                        continue
                    seen.add((href, s))
                    t = m.group(2) and m.group(2).zfill(5)
                    ev = {"date": m.group(1), "time": t if t and t != "00:00" else None, "title": title, "url": href}
                    m = re.search(r"€\s*(\d[\d.,]*)", _peppered_price(unit) or _peppered_price(card))
                    if m and prijzen.bedrag(m.group(1)) is not None:
                        ev["price"] = prijzen.bedrag(m.group(1))  # laagste prijs (eerste bedrag: '€ 35,50–€ 37,50')
                    if re.search(r"uitverkocht|soldout|sold-out|wachtlijst", st):
                        ev["status"] = "sold"
                    if re.search(r"geannuleerd|afgelast|cancel", st):
                        ev["status"] = "cancelled"
                    out.append(ev)
        nxt = soup.select_one("a[rel=next][href]") or soup.find("link", rel="next")
        nxt = nxt.get("href") if nxt else None
        url = (nxt if nxt.startswith("http") else site + nxt).split("#")[0] if nxt else None
    log(f"  {src['name']}: {pages} agendapagina's, {cards} kaarten (peppered)")
    return out if cards else None


def _wp_prijs(acf):
    """Laagste prijs uit ACF: Leiden 'prices' [{"price": "42.5"}], Kunstmin 'ranks' [{"price": "44,00"}]. Alleen bedragen > 0."""
    bedragen = []
    for k in ("prices", "ranks"):
        for r in acf.get(k) or []:
            try:
                x = float(str((r or {}).get("price") or "").replace(",", "."))
            except ValueError:
                continue
            if 0 < x < 1000:
                bedragen.append(x)
    return min(bedragen) if bedragen else None


def wp_shows(src, F, cfg, log):
    """WordPress met ACF-voorstellingen (Leidse Schouwburg & Stadsgehoorzaal, Kunstmin): /wp-json/wp/v2/show geeft per
    voorstelling acf.events[] met start_date "20270925", start_time "20:15:00" en een status. Alle speeldata in een
    paar verzoeken, zonder honderden voorstellingspagina's."""
    api = src.get("wp_api") or _site(src) + "/wp-json/wp/v2/show"
    out, vandaag = [], TODAY.strftime("%Y%m%d")
    for page in range(1, 11):
        data = F.get_json(api, {"per_page": 100, "page": page, "_fields": "id,link,title,acf"})
        if not isinstance(data, list) or not data:
            if page == 1:
                return None   # site herkent dit niet (meer): de gewone uitlezer (links_json) neemt het over
            break
        for show in data:
            acf = show.get("acf") if isinstance(show, dict) else None
            if not isinstance(acf, dict) or not isinstance(show.get("link"), str):
                continue
            titel = re.sub(r"<[^>]+>", "", unescape(unescape(str((show.get("title") or {}).get("rendered") or "")))).strip()
            if not titel:
                continue
            prijs = _wp_prijs(acf)
            for ev in acf.get("events") or []:
                if not isinstance(ev, dict):
                    continue
                d, t = str(ev.get("start_date") or ""), str(ev.get("start_time") or "")
                if not re.fullmatch(r"20\d{6}", d) or d < vandaag:
                    continue
                e = {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "time": t[:5] if re.match(r"\d\d:\d\d", t) else None,
                     "title": titel, "url": show["link"]}
                status = str(ev.get("status") or "").lower()
                if re.search(r"uitverkocht|sold|wait_?list|wachtlijst", status):
                    e["status"] = "sold"
                elif re.search(r"geannuleerd|afgelast|cancel", status):
                    e["status"] = "cancelled"
                if prijs is not None:
                    e["price"] = prijs
                out.append(e)
        if len(data) < 100:
            break
    return out


AFAS_ROL = re.compile(r"^(?:support(?:[ -]?acts?)?|opener|(?:very\s+)?special\s+guests?|voorprogramma|gast(?:act)?)\b[\s:–-]*", re.I)
AFAS_START = re.compile(r"^(?:aanvang|start|begin)\b[\s:–-]*", re.I)
AFAS_KAAL = re.compile(r"^(?:de\s+|het\s+)?(?:show|concert|voorstelling|programma|optreden|hoofdact|hoofdprogramma|main\s*act|headliner)?$", re.I)
AFAS_DATUM = re.compile(r"\b(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})\b", re.I)
AFAS_V = 1  # ophogen als afas_detail iets anders teruggeeft (dan worden gecachte pagina's opnieuw gelezen)


def _hhmm(txt):
    m = HHMM.search(txt or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def afas_tijdschema(rows, title):
    """Tijdschema van AFAS Live [('Deuren open', '18:30 uur'), ('Aanvang support: Tsatsamis', '20:00 uur'),
    ('Aanvang: Jessie Ware', '21:00 uur'), ('Verwacht einde show', '22:45 uur')] -> {"doors", "start", "support", "times", "tot"}.
    'Aanvang', 'Aanvang show' en 'Start Show' zonder naam zijn de hoofdact (naam = de titel); 'Opener', 'Special guest' en
    'Support' zijn voorprogramma. De regels staan niet altijd op volgorde (eindtijd soms bovenaan)."""
    out, acts = {}, []
    for label, t in rows:
        t = _hhmm(t)
        label = " ".join((label or "").split()).strip(" :-–")
        if not t or not label or re.search(r"\bvip\b|meet ?(&|and|n) ?greet|\bm&g\b|early entry", label, re.I):
            continue
        if re.search(r"eind|\bend\b|curfew", label, re.I):
            out.setdefault("tot", t)
        elif DOORS_RE.search(label):
            out.setdefault("doors", t)
        else:
            rest, sup = AFAS_START.sub("", label), False
            if AFAS_ROL.match(rest):
                rest, sup = AFAS_ROL.sub("", rest).strip(" :-–"), True
            elif rest == label:
                continue  # geen 'Aanvang ...' en geen voorprogramma: pauze, signeersessie e.d.
            if AFAS_KAAL.match(rest):
                if sup:
                    continue  # 'Aanvang support' zonder naam
                rest = title
            if len(rest) <= 80:
                acts.append({"a": rest, "s": t, "sup": sup})
    if not acts:
        return out
    mn = lambda x: int(x["s"][:2]) * 60 + int(x["s"][3:])
    laat = max(mn(x) for x in acts) >= 720
    acts.sort(key=lambda x: mn(x) + 1440 if laat and mn(x) < 360 else mn(x))  # 00:30 komt na 23:00
    hoofd = next((i for i, x in enumerate(acts) if not x["sup"]), None)
    sup = [x["a"] for i, x in enumerate(acts) if x["sup"] and (hoofd is None or i < hoofd)]
    if sup:
        out["support"] = sup[:6]
    if hoofd is not None:  # zonder hoofdact in het schema geen blokken: de app zou de laatste act als hoofdact tonen
        out["start"] = acts[hoofd]["s"]
        out["times"] = [{"a": x["a"], "s": x["s"]} for x in acts[:12]]
    return out


def afas_detail(soup):
    """Voorstellingspagina van AFAS Live -> {"shows": [{"date", "time", "price", "rows"}], "support": [...]}.
    Elke speeldatum heeft een eigen uitklapblok (datum, eventueel tijd, prijzen) en een eigen tabblad in het tijdschema
    onderaan de pagina. De tekst van de pagina zelf lezen we niet: daar staat ook wanneer de voorverkoop begint."""
    shows = []
    for det in soup.select("div.dates details"):
        el = det.find("datetime") or det.find("date")
        m = AFAS_DATUM.search(el.get_text(" ", strip=True)) if el else None
        if not m or m.group(2).lower() not in _MON:
            continue
        try:
            d = dt.date(int(m.group(3)), _MON[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            continue
        tm = el.find("time")
        bedragen = [int(a) + (int(b) if b else 0) / 100 for li in det.select("ul li")
                    for a, b in re.findall(r"€\s*(\d{1,4})(?:[.,](\d{2}))?", li.get_text(" ", strip=True))]
        bedragen = [b for b in bedragen if 1 <= b <= 1000]
        shows.append({"date": d, "time": _hhmm(tm.get_text()) if tm else None, "price": min(bedragen) if bedragen else None, "rows": []})
    tt, tabs = soup.select_one("div.timesTable"), []
    for b in (tt.select("div.tab button") if tt else []):
        inh = tt.find(id=b.get("data-tab")) if b.get("data-tab") else None
        rows = []
        for li in (inh.find_all("li") if inh else []):
            sp = li.find("span")
            if sp:
                tijd = sp.get_text(" ", strip=True)
                sp.extract()
                rows.append([li.get_text(" ", strip=True), tijd])
        m = re.search(r"\b(\d{1,2})\s+([a-z]{3})", b.get_text(" ", strip=True), re.I)
        txt = re.sub(r"^.*?\b\d{1,2}\s+[a-z]{3}[a-z]*\.?", "", b.get_text(" ", strip=True), flags=re.I)
        tabs.append({"dm": (int(m.group(1)), _MON.get(m.group(2).lower())) if m else None, "time": _hhmm(txt), "rows": rows})
    dm = lambda s: (int(s["date"][8:]), int(s["date"][5:7]))
    if len(tabs) == len(shows) and all(t["dm"] == dm(s) for t, s in zip(tabs, shows)):
        for t, s in zip(tabs, shows):
            s["rows"] = t["rows"]
    else:  # aantallen verschillen: alleen koppelen wat op datum (en tijd) eenduidig is
        for s in shows:
            kand = [t for t in tabs if t["dm"] == dm(s)]
            if len(kand) > 1:
                kand = [t for t in kand if t["time"] == s["time"]]
            if len(kand) == 1:
                s["rows"] = kand[0]["rows"]
    sup = []
    for li in soup.select("ul.act li"):
        naam = AFAS_ROL.sub("", " ".join(li.get_text(" ", strip=True).split())).strip(" :-–+")
        if naam and len(naam) <= 80 and not NO_ACT_RE.search(naam):
            sup.append(naam)
    return {"shows": shows, "support": sup[:6]}


def afas_show(rij, info, meerdere):
    """Eén regel uit de agenda + wat de voorstellingspagina over die speeldatum zegt -> event.
    Tijd: staat er een tijd bij de show zelf (twee shows op één dag, of '20:00' in het datumblok) dan is dat de aanvang;
    anders de eerste act uit het tijdschema, anders deuren open. Bij meer shows op één dag vertrouwen we een schema dat
    eerder begint dan de show niet (Freek Vonk: 'Aanvang 10:00' bij de show van 13:30)."""
    ev = {"date": rij["date"], "time": rij.get("time"), "title": rij["title"], "url": rij["url"]}
    if rij.get("status"):
        ev["status"] = rij["status"]
    if not info:
        return ev
    show, sup = info.get("show") or {}, info.get("support") or []
    lt = rij.get("time") or show.get("time")
    s = afas_tijdschema(show.get("rows") or [], rij["title"])
    eerste = s["times"][0]["s"] if s.get("times") else None
    if lt and meerdere:
        if eerste and eerste < lt:
            for k in ("times", "start", "support"):
                s.pop(k, None)
        ev["time"] = lt
    else:
        ev["time"] = eerste or lt or s.get("doors")
    if s.get("doors") and ev["time"] and s["doors"] > ev["time"]:
        s.pop("doors")
    ev.update(s)
    if sup and not ev.get("support") and not s.get("times"):
        ev["support"] = sup  # nog geen tijdschema: de namen die boven aan de pagina staan
    if show.get("price") is not None:
        ev["price"] = show["price"]
    return ev


def afaslive(src, F, cfg, log, cache=None):
    """AFAS Live: de agenda heeft per speeldatum een eigen regel met de kale naam ('Beth Hart', twee regels: 1 en 4 december;
    twee shows op één dag elk met hun tijd). De voorstellingspagina heet 'Beth Hart op 1 en 4 december 2026 in AFAS Live' en
    noemt in de tekst de start van de voorverkoop ('vrijdag om 10:00 uur'); de gewone uitlezer maakte daar één show op de
    laatste datum om 10:00 van. Daarom: naam, datum en uitverkocht uit de agenda, tijden en prijs uit het datumblok en het
    tijdschema van de voorstellingspagina (afas_detail). Lukt de agenda niet, dan een fout (geen terugval op de gewone
    uitlezer en geen halve lijst)."""
    html = F.get(src["agenda_url"])
    arts = BeautifulSoup(html, "html.parser").select("article.agendaV2-item") if html else []
    rijen = []
    for art in arts:
        a = art.select_one("a.rowMain[href]") or art.find("a", href=True)
        h = art.find(["h4", "h3", "h2"])
        if not a or not h:
            continue
        tm = h.find("time")
        tijd = _hhmm(tm.get_text()) if tm else None
        if tm:
            tm.extract()
        titel = " ".join(h.get_text(" ", strip=True).split())
        p = art.select_one("p.date") or art
        data = []
        for m in AFAS_DATUM.finditer(p.get_text(" ", strip=True)):
            try:
                data.append(dt.date(int(m.group(3)), _MON[m.group(2).lower()], int(m.group(1))))
            except (ValueError, KeyError):
                pass
        if not titel or not data:
            continue
        d = data[-1]  # verplaatste show: eerst de oude datum, dan de nieuwe
        klassen, tekst = " ".join(art.get("class") or []), art.get_text(" ", strip=True)
        status = "cancelled" if re.search(r"st-cancel|st-afgelast", klassen) or re.search(r"\b(afgelast|geannuleerd|gaat niet door)\b", tekst, re.I) \
            else "sold" if "st-soldout" in klassen or re.search(r"\buitverkocht\b", tekst, re.I) else None
        url = urljoin(src["agenda_url"], a["href"]).split("#")[0]
        if d >= TODAY:
            rijen.append({"date": d.isoformat(), "time": tijd, "title": titel, "url": url, "status": status})
    if not rijen:
        raise RuntimeError(f"AFAS Live: agenda niet gekregen of leeg (antwoorden: {F.stats.get('afaslive.nl', {})})")
    fresh = (TODAY - dt.timedelta(days=cfg.get("detail_refresh_days", 7))).isoformat()
    binnenkort = (TODAY + dt.timedelta(days=14)).isoformat()
    infos, opgehaald = {}, 0
    for u in dict.fromkeys(r["url"] for r in rijen):
        c = (cache or {}).get(u) or {}
        soon = min(r["date"] for r in rijen if r["url"] == u) <= binnenkort
        if (c.get("afas") or {}).get("v") == AFAS_V and c.get("at", "") >= fresh and not (soon and c.get("at") != TODAY.isoformat()):
            infos[u] = c["afas"]
            continue
        page = F.get(u)
        opgehaald += 1
        if not page:
            continue  # pagina lukt niet: de show blijft staan met wat de agenda geeft
        infos[u] = dict(afas_detail(BeautifulSoup(page, "html.parser")), v=AFAS_V)
        if cache is not None:
            cache[u] = {"at": TODAY.isoformat(), "v": 0, "ev": None, "afas": infos[u]}
    out, gebruikt = [], {}
    per_dag = {}
    for r in rijen:
        per_dag[(r["url"], r["date"])] = per_dag.get((r["url"], r["date"]), 0) + 1
    for r in rijen:
        info = infos.get(r["url"])
        show = None
        if info:
            kand = [s for s in info["shows"] if s["date"] == r["date"]]
            if r["time"] and any(s["time"] == r["time"] for s in kand):
                kand = [s for s in kand if s["time"] == r["time"]]
            if kand:  # zelfde datum zonder tijd in de agenda: op volgorde
                i = gebruikt.get((r["url"], r["date"], r["time"]), 0)
                show = kand[min(i, len(kand) - 1)]
                gebruikt[(r["url"], r["date"], r["time"])] = i + 1
        out.append(afas_show(r, {"show": show, "support": info["support"]} if info else None, per_dag[(r["url"], r["date"])] > 1))
    log(f"  {src['name']}: {len(rijen)} speeldata op {len(infos)} pagina's ({opgehaald} opgehaald)")
    return out


PLATFORMS = {"paradiso": paradiso, "ziggodome": ziggodome, "melkweg": melkweg, "tolhuistuin": tolhuistuin, "musis": musis,
             "cre8ion": cre8ion, "render_api": render_api, "umbraco_agenda": umbraco_agenda,
             "umbraco_getshows": umbraco_getshows, "itix": itix, "peppered": peppered, "wp_shows": wp_shows, "afaslive": afaslive}


MET_CACHE = {"afaslive"}  # uitlezers die voorstellingspagina's ophalen en daarvoor de detail-cache gebruiken


def scrape(src, F, cfg, log, cache=None):
    fn = PLATFORMS[src["platform"]]
    evs = fn(src, F, cfg, log, cache) if src["platform"] in MET_CACHE else fn(src, F, cfg, log)
    if evs is None:  # platform herkent de site niet (meer): de gewone uitlezer neemt het over
        log(f"  {src['name']}: {src['platform']} gaf niets bruikbaars, terug naar de gewone uitlezer")
        return None
    evs = [e for e in evs if e["date"] >= TODAY.isoformat()]
    log(f"  {src['name']}: {len(evs)} items ({src['platform']})")
    return evs
