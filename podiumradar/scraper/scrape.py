"""Podiumradar: haalt de concert- en theateragenda van Nederland op en schrijft site/data.json.

Gebruik:
  python scraper/scrape.py                                           # volledige run
  python scraper/scrape.py --only noord-brabant --max-pages 2 --dry-run --dump /tmp/pr   # snelle test
"""
import argparse, datetime as dt, hashlib, json, pathlib, re, sys, time
from html import unescape
from urllib import robotparser
import requests
from bs4 import BeautifulSoup
import sources

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "scraper/config.json").read_text(encoding="utf-8"))
OUT = ROOT / "site/data.json"
VCACHE = ROOT / "scraper/venues_cache.json"

ap = argparse.ArgumentParser()
ap.add_argument("--max-pages", type=int, default=CFG["max_pages_per_list"])
ap.add_argument("--dry-run", action="store_true", help="niets wegschrijven, alleen tonen")
ap.add_argument("--dump", help="map om opgehaalde HTML te bewaren (om selectors te controleren)")
ap.add_argument("--no-details", action="store_true")
ap.add_argument("--only", help="alleen deze provincie-slug (test)")
ap.add_argument("--source", help="alleen bronnen waarvan de naam dit bevat (test)")
ap.add_argument("--podiuminfo", action="store_true", help="podiuminfo.nl ook meenemen (werkt niet vanaf GitHub)")
ARGS = ap.parse_args()

S = requests.Session()
S.headers["User-Agent"] = CFG["user_agent"]
# robots.txt ophalen met onze eigen User-Agent: RobotFileParser.read() gebruikt
# de standaard Python-UA, krijgt dan een 403 en verbiedt vervolgens alles.
RP = robotparser.RobotFileParser()
try:
    _r = S.get(CFG["base"] + "/robots.txt", timeout=30)
    if _r.status_code == 200:
        RP.parse(_r.text.splitlines())
    else:
        RP = None
except requests.RequestException:
    RP = None
_last = [0.0]


def get(url):
    if RP and not RP.can_fetch(CFG["user_agent"], url):
        print("  robots.txt staat dit niet toe:", url)
        return None
    wait = CFG["delay_seconds"] - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    try:
        r = S.get(url, timeout=30)
    except requests.RequestException as e:
        print("  fout:", url, e)
        return None
    if r.status_code != 200:
        print("  status", r.status_code, url)
        return None
    if ARGS.dump:
        p = pathlib.Path(ARGS.dump)
        p.mkdir(parents=True, exist_ok=True)
        (p / (re.sub(r"[^a-z0-9]+", "_", url.lower())[-120:] + ".html")).write_text(r.text, encoding="utf-8")
    return r.text


LINK_RE = re.compile(r"/(concert|cabaret/voorstelling|festival)/(\d+)/")
TITLE_RE = re.compile(r"^(Concert|Event|Cabaret|Festival)\s+(.*)\s+in\s+(.+)$", re.S)
TODAY = dt.date.today()
HORIZON = TODAY + dt.timedelta(days=CFG["days_ahead"])


FULL_MONTHS = {m: i + 1 for i, m in enumerate(
    "januari februari maart april mei juni juli augustus september oktober november december".split())}
# aria-label van elke agendalink, bv.
# "Concert PAUW, woensdag 30 september 2026 om 20:00, Mezz, Breda, tickets beschikbaar"
ARIA_RE = re.compile(r",\s*(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\s+(\d{1,2})\s+("
                     + "|".join(FULL_MONTHS) + r")\s+(\d{4})(?:\s+om\s+([01]\d|2[0-3]):([0-5]\d))?,\s*(.*)$", re.I | re.S)


def parse_listing(html):
    """Leest elke agendalink uit via zijn title (soort, titel, podium) en aria-label (datum, tijd, plaats)."""
    soup = BeautifulSoup(html, "html.parser")
    events, last = {}, None
    for node in soup.find_all("a", href=True, attrs={"aria-label": True}):
        lm = LINK_RE.search(node["href"])
        tm = TITLE_RE.match(unescape(node.get("title") or "").strip())
        am = ARIA_RE.search(unescape(node["aria-label"]))
        if not lm or not tm or not am:
            continue
        kind = {"concert": "p", "cabaret/voorstelling": "c", "festival": "f"}[lm.group(1)]
        eid = kind + lm.group(2)
        if eid in events:
            continue
        try:
            d = dt.date(int(am.group(3)), FULL_MONTHS[am.group(2).lower()], int(am.group(1)))
        except ValueError:
            continue
        last = max(last, d) if last else d
        t = f"{am.group(4)}:{am.group(5)}" if am.group(4) else None
        venue = tm.group(3).strip()
        rest = am.group(6).strip()
        # Na het podium volgt de plaats; het podium zelf kan ook komma's bevatten.
        rest = rest[len(venue):].lstrip(", ") if rest.startswith(venue) else rest.split(",", 1)[-1].strip()
        city = rest.split(",")[0].strip() or None
        title = re.sub(r"(Event|Cabaret|Festival)$", "", tm.group(2)).strip()
        href = node["href"] if node["href"].startswith("http") else CFG["base"] + node["href"]
        ev = {"id": eid, "date": d.isoformat(), "time": t, "title": title,
              "venue": venue, "city": city, "kind": tm.group(1), "url": href}
        if "uitverkocht" in rest.lower():
            ev["status"] = "sold"
        events[eid] = ev
    return events, last


def crawl(path, label):
    found = {}
    for n in range(1, ARGS.max_pages + 1):
        url = f"{CFG['base']}{path}" + (f"?page={n}" if n > 1 else "")
        html = get(url)
        if not html:
            break
        ev, last = parse_listing(html)
        new = {k: v for k, v in ev.items() if k not in found}
        found.update(new)
        print(f"  {label} p{n}: {len(new)} nieuw, t/m {last}")
        if not new or (last and last > HORIZON) or f"page={n + 1}" not in html:
            break
    return found


def detail(ev):
    html = get(ev["url"])
    if not html:
        return
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find(id=re.compile("content|main", re.I)) or soup
    txt = main.get_text("\n", strip=True)

    def grab(pat):
        m = re.search(pat + r"\D{0,20}?([01]?\d|2[0-3])[:.]([0-5]\d)", txt, re.I)
        return f"{int(m.group(2)):02d}:{m.group(3)}" if m else None

    ev["doors"] = grab(r"(deuren open|zaal open|deur open|doors)")
    ev["start"] = grab(r"(aanvang|start concert|showtime)")
    m = re.search(r"(voorprogramma|support|special guests?)\s*[:\-]?\s*([^\n]{2,80})", txt, re.I)
    if m:
        sup = re.split(r"\s*(?:,|&|\+| en )\s*", m.group(2).strip(" .:"))
        ev["support"] = [s for s in sup if 1 < len(s) < 50][:3]
    sold = main.find(class_=re.compile(r"uitverkocht|soldout|sold-out", re.I))
    if sold:
        ev["status"] = "sold"


def geocode(name, city, cache):
    key = f"{name}|{city}"
    if key in cache:
        return cache[key]
    for q in (f"{name}, {city}, Nederland", f"{city}, Nederland"):
        time.sleep(1.1)
        try:
            js = S.get("https://nominatim.openstreetmap.org/search",
                       params={"q": q, "format": "json", "limit": 1}, timeout=20).json()
        except Exception:
            js = []
        if js:
            cache[key] = [round(float(js[0]["lat"]), 4), round(float(js[0]["lon"]), 4)]
            return cache[key]
    cache[key] = None
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]


GENRE_WORDS = [  # (genre, trefwoorden in titel) - eerste treffer wint
    ("Musical", ["musical"]), ("Opera", ["opera"]), ("Dans", ["dans", "ballet", "dance company"]),
    ("Cabaret", ["cabaret", "comedy", "stand-up", "standup", "try-out", "oudejaars"]),
    ("Klassiek", ["symfon", "orkest", "philharmon", "strijkkwartet", "kamermuziek", "concertgebouw", "requiem",
                  "passion", "matthäus", "bach", "mozart", "beethoven", "recital", "koor"]),
    ("Jazz", ["jazz", "big band", "bigband"]), ("Jeugd", ["kinder", "familie", "(4+)", "(6+)", "(8+)", "jeugd"]),
    ("Tribute", ["tribute", "undercover", "coverband", "plays the music of", "a tribute", "celebrating"]),
    ("Feest", ["party", "feest", "fuif", "silent disco", "jukebox", "bingo", "afterparty", "karaoke"]),
    ("Dance", ["techno", "house", " dj", "rave", "hardstyle", "drum & bass", "dnb"]),
    ("Metal", ["metal", "doom", "sludge", "grindcore"]), ("Punk", ["punk", "hardcore"]),
    ("Nederlandstalig", ["hollandse", "toppers", "nederlandstalig", "smartlap"]),
    ("Film", ["film", "cinema", "screening"]), ("Lezing", ["lezing", "talk", "podcast", "debat", "college"]),
    ("Toneel", ["toneel", "voorstelling", "theater"]),
]
DEFAULT_GENRE = {"pop": "Overig", "concert": "Klassiek", "arena": "Overig", "cafe": "Overig",
                 "thea": "Theater", "museum": "Tentoonstelling", "festival": "Festival", "film": "Film"}


def guess_genre(title, vtype):
    low = " " + title.lower()
    for g, words in GENRE_WORDS:
        if any(w in low for w in words):
            return g
    return DEFAULT_GENRE.get(vtype, "Overig")


def norm(t):
    return re.sub(r"[^a-z0-9]+", "", unescape(t).lower())[:14]


def podiuminfo_events():
    events = {}
    provs = {k: v for k, v in CFG["provinces"].items() if not ARGS.only or k == ARGS.only}
    for s, name in provs.items():
        print("Provincie", name)
        for eid, ev in crawl(f"/concertagenda/{s}/", name).items():
            ev["prov"] = name
            events.setdefault(eid, ev)
    print("Genres")
    for s, g in CFG["genres"].items():
        for eid in crawl(f"/concertagenda/genre/{s}/", g):
            if eid in events and "genre" not in events[eid]:
                events[eid]["genre"] = g
    for ev in events.values():
        if "genre" not in ev:
            ev["genre"] = {"Cabaret": "Cabaret", "Event": "Feest"}.get(ev["kind"], "Overig")
    events = {k: v for k, v in events.items() if TODAY.isoformat() <= v["date"] <= HORIZON.isoformat()}

    if not ARGS.no_details:
        until = (TODAY + dt.timedelta(days=CFG["detail_days"])).isoformat()
        soon = sorted((e for e in events.values() if e["date"] <= until and e["kind"] in ("Concert", "Cabaret")),
                      key=lambda e: e["date"])[:CFG["detail_max"]]
        print(f"Details voor {len(soon)} shows")
        for e in soon:
            detail(e)
            # Tijd van de detailpagina is betrouwbaarder dan die uit de lijst
            # (lijst toont soms de laatste set of een verkeerde tijd).
            if e.get("start") or e.get("doors"):
                e["time"] = e.get("start") or e.get("doors")
    for e in events.values():
        low = e["venue"].lower()
        e["vtype"] = CFG["venue_type_overrides"].get(e["venue"]) or \
            ("thea" if any(k in low for k in CFG["theater_keywords"]) else "pop")
    return events


def own_events():
    """Events van de eigen sites van podia, theaters, musea en festivals (scraper/bronnen.json)."""
    events, seen = {}, set()
    for src, evs in sources.collect(CFG, only=ARGS.source):
        for ev in evs:
            # Zelfde voorstelling via twee bronnen (bv. dubbel in de lijst): één keer tonen
            key = (ev["url"].split("?")[0].rstrip("/"), ev["date"], ev.get("time"))
            if key in seen:
                continue
            seen.add(key)
            e = dict(ev, venue=src["name"], city=src.get("city", ""), prov=src.get("prov", ""),
                     vtype=src.get("type", "pop"), kind=src.get("type", "pop"))
            e["genre"] = src.get("genre") or guess_genre(e["title"], e["vtype"])
            e["id"] = "s" + hashlib.sha1(f"{src['name']}|{e['date']}|{e['title']}".encode()).hexdigest()[:10]
            events[e["id"]] = e
    return events


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"events": []}
    first_seen = {e["id"]: e.get("first_seen", TODAY.isoformat()) for e in prev.get("events", [])}

    events = own_events()
    print(f"Eigen bronnen: {len(events)} items")
    if CFG.get("use_podiuminfo") or ARGS.podiuminfo:
        # Podiuminfo vult alleen aan: wat we al van de eigen site hebben, slaan we over.
        have = {(slug(e["venue"] + "-" + e["city"]), e["date"], norm(e["title"])) for e in events.values()}
        extra = podiuminfo_events()
        for eid, e in extra.items():
            if (slug(e["venue"] + "-" + (e["city"] or "")), e["date"], norm(e["title"])) not in have:
                events.setdefault(eid, e)
        print(f"Podiuminfo: {len(extra)} items opgehaald")

    # Houd wat nog loopt of binnen de horizon begint (tentoonstellingen en festivals lopen soms al).
    t0, hz = TODAY.isoformat(), HORIZON.isoformat()
    hz_long = (TODAY + dt.timedelta(days=400)).isoformat()  # festivals en tentoonstellingen worden ver vooruit aangekondigd
    events = {k: v for k, v in events.items() if (v.get("end") or v["date"]) >= t0
              and v["date"] <= (hz_long if v["vtype"] in ("festival", "museum") else hz)}

    cache = json.loads(VCACHE.read_text(encoding="utf-8")) if VCACHE.exists() else {}
    venues, budget = {}, CFG["geocode_max_per_run"]
    for e in events.values():
        city = e["city"] or ""
        vid = slug(e["venue"] + "-" + city)
        if vid not in venues:
            key = f"{e['venue']}|{city}"
            if key not in cache and budget > 0:
                budget -= 1
                geocode(e["venue"], city or e["prov"], cache)
            ll = cache.get(key)
            venues[vid] = {"name": e["venue"], "city": city, "prov": e["prov"], "type": e["vtype"],
                           "lat": ll[0] if ll else None, "lon": ll[1] if ll else None}
        e["v"] = vid
        e["first_seen"] = first_seen.get(e["id"], TODAY.isoformat())
        for k in ("venue", "city", "prov", "kind", "vtype"):
            e.pop(k, None)

    out = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "venues": venues,
           "events": sorted(events.values(), key=lambda e: (e["date"], e["time"] or "99"))}
    n_prev, n_new = len(prev.get("events", [])), len(out["events"])
    print(f"Klaar: {n_new} items op {len(venues)} locaties (vorige keer {n_prev})")
    no_time = sum(1 for e in out["events"] if not e["time"])
    no_city = sum(1 for v in venues.values() if not v["city"])
    print(f"Controle: {no_time} shows zonder tijd, {no_city} podia zonder plaats")

    if ARGS.dry_run:
        print(json.dumps(out["events"][:5], ensure_ascii=False, indent=1))
        return
    VCACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    if n_new == 0:
        print("Niets gevonden; data.json NIET overschreven.")
        sys.exit(3)
    if n_prev and n_new < n_prev * CFG["min_ratio_vs_previous"] and not ARGS.only:
        print("Veel minder shows dan vorige keer; mogelijk is de bronsite veranderd. data.json NIET overschreven.")
        sys.exit(2)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
