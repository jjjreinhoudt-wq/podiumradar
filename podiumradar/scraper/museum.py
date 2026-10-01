"""Tentoonstellingen: één item per tentoonstelling met begin- en einddatum ("t/m ...").

- exhibition_period(txt): vindt de eerste periode in een tekst, in de vele schrijfwijzen die musea gebruiken.
- from_text_museum(soup, url): uitlezer voor een tentoonstellingspagina (in plaats van sources.from_text).
- PLATFORMS: eigen uitlezers voor musea met een eigen API ("platform" in bronnen.json).
"""
import datetime as dt, html as H, json, re
from zoneinfo import ZoneInfo

TODAY = dt.date.today()
NL = ZoneInfo("Europe/Amsterdam")
MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}

MN = r"(jan|feb|mrt|maa|mar|apr|mei|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.?"
D_TXT = r"(\d{1,2})\s+" + MN + r"(?:\s+'?(\d{4}))?"            # dag, maand, jaar?
D_NUM = r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})"
SEP = r"\s*(?:\|\s*)*(?:t/m|t\.m\.|tot en met|tot|until|till|to|through|[-–—]|\|)\s*(?:\|\s*)*(?:[a-z]{2,9}\.?\s+)?"
GAP = r"\s*(?:\|\s*)*(?:(?:tot en met|t/m|tot|until)\s*(?:\|\s*)*)?"  # "20 sep 2026 | 28 feb 2027"
PAT_TT = re.compile(D_TXT + r"(?:" + SEP + r"|" + GAP + r")" + D_TXT, re.I)      # 4 juni 2026 t/m 1 nov 2026
PAT_DT = re.compile(r"\b(\d{1,2})" + SEP + D_TXT, re.I)                           # 4 t/m 14 juni 2026
PAT_NN = re.compile(D_NUM + r"(?:" + SEP + r"|" + GAP + r")" + D_NUM)            # 19.05.2026 t/m 28.02.2027
PAT_N2 = re.compile(r"\b(\d{1,2})[./](\d{1,2})\s*[-–—]\s*" + D_NUM)              # 14.06-27.09.2026
PAT_UNTIL = re.compile(r"(?:t/m|t\.m\.|tot en met|nog tot|tot|until|through|te zien tot)\s*(?:\|\s*)*(?:[a-z]{2,9}\.?\s+)?(?:"
                       + D_TXT + r"|" + D_NUM + r")", re.I)
PAT_FROM = re.compile(r"(?:vanaf|from|opent|opening|te zien vanaf|start)\s*(?:\|\s*)*(?:[a-z]{2,9}\.?\s+)?(?:"
                      + D_TXT + r"|" + D_NUM + r")", re.I)


def _mk(day, mon, yy, ref_year=None):
    m = int(mon) if str(mon).isdigit() else MONTHS[mon.lower()[:3]]
    return dt.date(int(yy) if yy else (ref_year or TODAY.year), m, int(day))


def _fix_year(d, yy):
    """Datum zonder jaartal die ruim voorbij is, valt volgend jaar."""
    return d.replace(year=d.year + 1) if not yy and d < TODAY - dt.timedelta(days=60) else d


def exhibition_period(txt):
    """(start, end) van de eerste periode in de tekst. start None = loopt al ('t/m ...'), end None = onbekend."""
    found = []
    for m in PAT_TT.finditer(txt):
        try:
            b = _fix_year(_mk(m.group(4), m.group(5), m.group(6)), m.group(6))
            a = _mk(m.group(1), m.group(2), m.group(3), b.year)
            if not m.group(3) and a > b:
                a = a.replace(year=a.year - 1)
        except ValueError:
            continue
        if a <= b and (b - a).days < 366 * 12:
            found.append((m.start(), a, b))
            break
    for m in PAT_DT.finditer(txt):
        try:
            b = _fix_year(_mk(m.group(2), m.group(3), m.group(4)), m.group(4))
            a = b.replace(day=int(m.group(1)))
        except ValueError:
            continue
        if a <= b:
            found.append((m.start(), a, b))
            break
    for m in PAT_NN.finditer(txt):
        try:
            a, b = _mk(m.group(1), m.group(2), m.group(3)), _mk(m.group(4), m.group(5), m.group(6))
        except ValueError:
            continue
        if a <= b:
            found.append((m.start(), a, b))
            break
    for m in PAT_N2.finditer(txt):
        try:
            b = _mk(m.group(3), m.group(4), m.group(5))
            a = _mk(m.group(1), m.group(2), None, b.year)
        except ValueError:
            continue
        if a <= b:
            found.append((m.start(), a, b))
            break
    for m in PAT_UNTIL.finditer(txt):
        try:
            if m.group(1):
                b = _mk(m.group(1), m.group(2), m.group(3))
                if not m.group(3):
                    # Jaar ontbreekt: neem het jaar van een volledige datum kort ervoor ("19 april 2026 ... t/m 17 mei")
                    prev = [p for p in re.finditer(D_TXT, txt[max(0, m.start() - 400):m.start()], re.I) if p.group(3)]
                    if prev:
                        a0 = _mk(prev[-1].group(1), prev[-1].group(2), prev[-1].group(3))
                        b = b.replace(year=a0.year)
                        if b < a0:
                            b = b.replace(year=b.year + 1)
                        found.append((m.start(), a0, b))
                        break
                    b = _fix_year(b, None)
            else:
                b = _mk(m.group(4), m.group(5), m.group(6))
        except ValueError:
            continue
        found.append((m.start(), None, b))
        break
    for m in PAT_FROM.finditer(txt):
        try:
            a = _fix_year(_mk(m.group(1), m.group(2), m.group(3)), m.group(3)) if m.group(1) \
                else _mk(m.group(4), m.group(5), m.group(6))
        except ValueError:
            continue
        found.append((m.start() + 0.5, a, None))
        break
    if not found:
        return None
    pos, a, b = min(found, key=lambda f: f[0])
    if b is None:
        # "vanaf 9 oktober te zien ... t/m 4 april 2027": zoek een einddatum kort daarna
        m = PAT_UNTIL.search(txt, int(pos) + 1, int(pos) + 600)
        if m:
            try:
                e = _mk(m.group(1), m.group(2), m.group(3)) if m.group(1) else _mk(m.group(4), m.group(5), m.group(6))
                b = e if e > a else (e.replace(year=e.year + 1) if m.group(1) and not m.group(3) else None)
            except ValueError:
                pass
    return a, b


def _clean_txt(node):
    # Vue/Nuxt-sites (Van Gogh Museum) zetten de inhoud in <template>: bs4 slaat die tekst anders over
    from bs4.element import NavigableString, CData, TemplateString
    for bad in node.find_all(["nav", "footer", "script", "style", "form", "noscript"]):
        bad.decompose()
    txt = node.get_text("\n", strip=True, types=(NavigableString, CData, TemplateString))
    return re.sub(r"\s*\n\s*", " | ", txt)


def from_text_museum(soup, url):
    from sources import pick_title
    title = pick_title(soup, url)
    h1 = soup.find("h1")
    h1_txt = h1.get_text(" ", strip=True) if h1 else ""
    # "21 mei t/m 5 juli 2026 | Expositie X" -> "Expositie X"
    if "|" in h1_txt and (exhibition_period(h1_txt.split("|")[0]) or
                          re.fullmatch(r"\s*[\d\s,&en]*" + D_TXT + r"\s*", h1_txt.split("|")[0], re.I)):
        title = h1_txt.split("|", 1)[1].strip() or title
    # Titel in losse letters ("P l a y i n g H o u s e"): aria-label of aaneen
    if title and re.fullmatch(r"(?:\S ){3,}\S", title) and h1:
        lab = h1.get("aria-label") or (h1.find(attrs={"aria-label": True}) or {}).get("aria-label")
        title = lab or re.sub(r"\s+", " ", h1.get_text("")).strip() or title
    # "14.06-27.09.2026 MATERIAL WORLDS" -> "MATERIAL WORLDS"
    if title:
        title = re.sub(r"^\s*\d{1,2}[./]\d{1,2}(?:[./]20\d{2})?\s*[-–—]\s*\d{1,2}[./]\d{1,2}[./]20\d{2}\s*[|:-]?\s*", "",
                       title) or title
    main = soup.find("main") or soup.find("article")
    per = exhibition_period(_clean_txt(main)[:6000]) if main else None
    if not per:
        per = exhibition_period(_clean_txt(soup.body or soup)[:12000])
    if not per or not title:
        return None
    a, b = per
    started = a is None
    if a is None:
        a = TODAY if b >= TODAY else b   # loopt al: vanaf vandaag te zien
    ev = {"date": a.isoformat(), "time": None, "title": title, "url": url}
    if started:
        ev["ongoing"] = True  # begindatum onbekend; id mag dan niet van de (wisselende) datum afhangen
    if b and b > a:
        ev["end"] = b.isoformat()
    return ev


# ---------------------------------------------------------------- eigen uitlezers per museum-platform

def _ev(d0, d1, title, url, t=None):
    ev = {"date": d0, "time": t, "title": H.unescape(title).strip(), "url": url}
    if d1 and d1 > d0:
        ev["end"] = d1
    return ev


def _base(src):
    m = re.match(r"https?://[^/]+", src.get("api_base") or src["agenda_url"])
    return m.group(0)


def sanity(src, F, cfg, log):
    """Next.js + Sanity (Teylers, Kröller-Müller, Frans Hals): POST /api/events, datums in dateSettings."""
    base = _base(src)
    cats = set(src.get("categories") or ["Tentoonstelling", "Collectiepresentatie", "Speciaal evenement", "Special event"])
    out, page = [], 1
    while page <= 20:
        d = F.post_json(base + "/api/events", {"languageCode": "nl", "page": page, "limit": 50, "excludedIds": []}) or {}
        for e in d.get("data") or []:
            if e.get("category") not in cats:
                continue
            ds, url = e.get("dateSettings") or {}, base + (e.get("url") or "")
            if ds.get("type") == "period":
                out.append(_ev(ds["startDate"][:10], (ds.get("endDate") or "")[:10], e["title"], url))
            elif ds.get("type") == "single":
                out.append(_ev(ds["date"][:10], None, e["title"], url, (ds.get("times") or {}).get("start")))
            elif ds.get("type") == "multiple":
                for x in ds.get("dates") or []:
                    if x["date"][:10] >= TODAY.isoformat():
                        out.append(_ev(x["date"][:10], None, e["title"], url, (x.get("times") or {}).get("start")))
        if not d.get("hasNextPage"):
            break
        page += 1
    return out


def textielmuseum(src, F, cfg, log):
    d = F.get_json("https://admin.textielmuseum.nl/api/exhibitions") or {}

    def local(s):  # "2026-03-27T23:00:00.000000Z" = middernacht Nederlandse tijd
        return dt.datetime.fromisoformat(re.sub(r"\.\d+", "", s).replace("Z", "+00:00")).astimezone(NL).date().isoformat()
    out = []
    for e in (d.get("current_exhibitions") or []) + (d.get("future_exhibitions") or []):
        name = e["name"]["nl"] if isinstance(e["name"], dict) else e["name"]
        slug = e["slug"]["nl"] if isinstance(e["slug"], dict) else e["slug"]
        out.append(_ev(local(e["start"]), local(e["finish"]), re.sub(r"^(Verwacht|Binnenkort)\s*[-–:]\s*", "", name),
                       "https://textielmuseum.nl/tentoonstellingen/" + slug))
    return out


def kirby_json(src, F, cfg, log):
    """Kirby CMS (Museum Arnhem): <agenda_url>.json met children[].dates als tekst."""
    d = F.get_json(src.get("api_url") or src["agenda_url"].rstrip("/") + ".json") or {}
    out = []
    for c in d.get("children") or []:
        per = exhibition_period(c.get("dates") or "")
        if per:
            a, b = per
            a = a or TODAY
            out.append(_ev(a.isoformat(), b.isoformat() if b else None, c["title"], c.get("url") or src["agenda_url"]))
    return out


def valkhof(src, F, cfg, log):
    """Vue-props in de HTML: "url", "title" en "date" ("06.06 – 15.11.2026")."""
    h = H.unescape(F.get(src["agenda_url"]) or "")
    out, seen = [], set()
    for m in re.finditer(r'"url":"(https?://[^"]+/agenda/[^"]+)","title":"([^"]+)"', h):
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        dm = re.search(r'"date":"([^"]*)"', h[m.end():m.end() + 3000])
        mm = re.match(r"(\d{2})\.(\d{2})(?:\.(\d{4}))?\s*[–-]\s*(\d{2})\.(\d{2})\.(\d{4})", dm.group(1) if dm else "")
        if not mm:
            continue
        b = dt.date(int(mm.group(6)), int(mm.group(5)), int(mm.group(4)))
        a = dt.date(int(mm.group(3) or b.year), int(mm.group(2)), int(mm.group(1)))
        if a > b:
            a = a.replace(year=a.year - 1)
        out.append(_ev(a.isoformat(), b.isoformat(), m.group(2), m.group(1).replace("\\/", "/")))
    return out


def zotonic(src, F, cfg, log):
    """Driebit Ginger/Zotonic (Nederlands Openluchtmuseum): /data/search?cat=..."""
    base, out = _base(src), []
    for cat in src.get("categories") or ["event_museum_exhibition", "event_museum_event"]:
        d = F.get_json(base + "/data/search", {"cat": cat, "filter": "event_dates>=" + TODAY.isoformat(), "limit": 100}) or {}
        for r in d.get("result") or []:
            ds = sorted(x[:10] for x in (r.get("properties") or {}).get("event_dates") or [] if x[:10] >= TODAY.isoformat())
            title = r["title"].get("nl") if isinstance(r.get("title"), dict) else r.get("title")
            if ds and title:
                out.append(_ev(ds[0], ds[-1], title, base + r.get("path", "")))
    return out


def statamic_graphql(src, F, cfg, log):
    """Statamic GraphQL (Zuiderzeemuseum): collectie 'events', type exhibition/event, geen vaste presentaties."""
    q = ('{ entries(collection: "events", limit: 500) { data { title url '
         '... on Entry_Events_Event { start_date date is_permanent type { value } } } } }')
    d = F.post_json(src["api_url"], {"query": q}) or {}
    site, out = _base(src), []
    for e in (((d.get("data") or {}).get("entries") or {}).get("data")) or []:
        if not (e.get("url") or "").startswith(src.get("url_prefix", "/zien-doen/")) or \
                (e.get("type") or {}).get("value") not in ("exhibition", "event"):
            continue
        a, b = (e.get("start_date") or "")[:10], (e.get("date") or "")[:10]
        if a and b and not e.get("is_permanent"):
            out.append(_ev(a, b, e["title"], site + e["url"]))
    return out


PLATFORMS = {"sanity": sanity, "textielmuseum": textielmuseum, "kirby_json": kirby_json, "valkhof": valkhof,
             "zotonic": zotonic, "statamic_graphql": statamic_graphql}


def scrape(src, F, cfg, log):
    evs = [e for e in PLATFORMS[src["platform"]](src, F, cfg, log) if (e.get("end") or e["date"]) >= TODAY.isoformat()]
    log(f"  {src['name']}: {len(evs)} items ({src['platform']})")
    return evs
