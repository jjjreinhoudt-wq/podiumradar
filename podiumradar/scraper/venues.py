"""Eigen uitlezers voor losse podia/theaters die hun agenda alleen via een eigen API of ingebedde JSON tonen.

Een bron in bronnen.json met "platform": "<naam>" (zie PLATFORMS) gaat hierheen.
Elke uitlezer geeft events {"date", "time", "title", "url", optioneel "doors", "status", "support"}.
"""
import datetime as dt, json, re
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
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


PLATFORMS = {"paradiso": paradiso, "ziggodome": ziggodome, "melkweg": melkweg, "tolhuistuin": tolhuistuin, "musis": musis,
             "cre8ion": cre8ion, "render_api": render_api, "umbraco_agenda": umbraco_agenda,
             "umbraco_getshows": umbraco_getshows, "itix": itix, "peppered": peppered}


def scrape(src, F, cfg, log):
    evs = PLATFORMS[src["platform"]](src, F, cfg, log)
    if evs is None:  # platform herkent de site niet (meer): de gewone uitlezer neemt het over
        log(f"  {src['name']}: {src['platform']} gaf niets bruikbaars, terug naar de gewone uitlezer")
        return None
    evs = [e for e in evs if e["date"] >= TODAY.isoformat()]
    log(f"  {src['name']}: {len(evs)} items ({src['platform']})")
    return evs
