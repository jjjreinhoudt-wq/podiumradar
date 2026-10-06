"""Podiumradar: haalt de concert- en theateragenda van Nederland op en schrijft site/data.json.

Gebruik:
  python scraper/scrape.py                                           # volledige run
  python scraper/scrape.py --only noord-brabant --max-pages 2 --dry-run --dump /tmp/pr   # snelle test
"""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, sys, time, unicodedata
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
ap.add_argument("--reclassify", action="store_true", help="alleen de genres in site/data.json opnieuw bepalen (zonder ophalen)")
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
    ("Jazz", ["jazz", "big band", "bigband"]), ("Jeugd", ["kindervoorstelling", "kinderconcert", "kinderfilm", "familievoorstelling", "familieconcert",
                                              "familiefilm", "familietheater", "(2+)", "(3+)", "(4+)", "(5+)", "(6+)", "(7+)",
                                              "(8+)", "(9+)", "(10+)", "jeugdtheater", "peuter", "kleuter"]),
    ("Tribute", ["tribute", "undercover", "coverband", "plays the music of", "a tribute", "celebrating"]),
    ("Feest", ["party", "feest", "fuif", "silent disco", "jukebox", "bingo", "afterparty", "karaoke"]),
    ("Dance", ["techno", "house", " dj", "rave", "hardstyle", "drum & bass", "dnb"]),
    ("Metal", ["metal", "doom", "sludge", "grindcore"]), ("Punk", ["punk", "hardcore"]),
    ("Nederlandstalig", ["hollandse", "toppers", "nederlandstalig", "smartlap"]),
    ("Lezing", ["lezing", "talk", "podcast", "debat", "college"]),
    ("Toneel", ["toneel", "voorstelling", "theater"]),
]
DEFAULT_GENRE = {"pop": "Overig", "concert": "Klassiek", "arena": "Overig", "cafe": "Overig",
                 "thea": "Theater", "museum": "Tentoonstelling", "festival": "Festival", "film": "Film"}


# Films, documentaires en filmvertoningen bij podia en theaters krijgen het genre "Film" (in de app standaard verborgen).
FILM_RE = re.compile(r"\b(films?|filmhuis\w*|filmclub|filmkring|film ?avond|filmmiddag|filmochtend|filmmatinee|film ?vertoning|"
                     r"filmvoorstelling|filmprogramma|filmreeks|film ?festival|film ?tour|\w+film|documentaires?|documentary|"
                     r"docu|albumovie|screening|vertoning|voorpremi[eè]re|movies that matter|kom movies|viewing party|bioscoop)\b",
                     re.I)
FILM_URL_RE = re.compile(r"/(films?|cinema|bioscoop|filmhuis|filmtheater)(/|$)", re.I)
FILM_YEAR_RE = re.compile(r"\((19[3-9]\d|20\d\d)\)")  # "Naked (1993)": zo zet o.a. de Melkweg films in de agenda
# Wel muziek: filmconcerten met live orkest/band, en stomme films met live begeleiding
LIVE_MUSIC_RE = re.compile(r"in concert|live[- ]to[- ]film|film ?concert|film ?muziek|film ?music|filmorkest|film orchestra|"
                           r"live[- ](soundtrack|score|muziek|begeleid\w*|gespeeld|orkest|op (het )?orgel)|met live|orkest|"
                           r"orchestra|symfon|symphon|sing[- ]?along|meezing|cinemusic|stomme film|stille film|silent film|"
                           r"\((18\d\d|19[0-2]\d)\)|eigen film", re.I)


def is_film(title, url="", vtype="", screening=False):
    """Film, documentaire of filmvertoning (en geen filmconcert met live muziek)?"""
    if vtype == "film":
        return True
    if vtype == "museum":  # tentoonstellingen over film zijn geen film; alleen echte vertoningen
        return bool(screening or re.search(r"film ?vertoning|screening|film ?avond|filmmiddag", title, re.I))
    slug = re.sub(r"[-_]+", " ", url.split("?")[0].rstrip("/").rsplit("/", 1)[-1])
    title = re.sub(r"\s\|\s[^|—]*$", "", title)  # "... | Lodewijk Films" is de maker, niet het soort voorstelling
    if LIVE_MUSIC_RE.search(title) or LIVE_MUSIC_RE.search(slug):
        return False
    return bool(screening or FILM_RE.search(title) or FILM_RE.search(slug) or FILM_URL_RE.search(url.split("?")[0])
                or FILM_YEAR_RE.search(title))


def film_key(title):
    """'FILMHUIS HOOFDDORP: Pressure' / 'Filmkring: Sense and Sensibility (2025)' -> 'pressure' / 'senseandsensibility'."""
    t = re.sub(r"^(film\w*|beschouwfilm|film ?&[^:]*)(\s+[^:]{0,25})?:\s*", "", unescape(title), flags=re.I)
    t = re.split(r"\s+[—|]\s+|\s+-\s+", t)[0]
    t = re.sub(r"\((19|20)\d\d\)|\((voor)?premi[eè]re\)", "", t, flags=re.I)
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9]", "", t)


def mark_known_films(items):
    """items: [(event, podiumnaam, soort)]. Podia met een filmhuis (Cacaofabriek, ECI, Groene Engel...) zetten films
    zonder herkenbare titel tussen de concerten. Staat dezelfde titel bij een bioscoop of elders al als film,
    dan is het daar ook een film. Alleen bij podia die aantoonbaar films draaien, zodat een band met een filmnaam blijft staan."""
    films, film_venues = set(), set()
    for e, venue, vtype in items:
        if e["genre"] == "Film":
            film_venues.add(venue)
            k = film_key(e["title"])
            if len(k) >= 4:
                films.add(k)
    n = 0
    for e, venue, vtype in items:
        if e["genre"] != "Film" and venue in film_venues and vtype not in ("museum", "festival") \
                and film_key(e["title"]) in films and not LIVE_MUSIC_RE.search(e["title"]):
            e["genre"], n = "Film", n + 1
    return n


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


def own_events(prev_events=()):
    """Events van de eigen sites van podia, theaters, musea en festivals (scraper/bronnen.json)."""
    events, seen = {}, set()
    for src, evs in sources.collect(CFG, only=ARGS.source):
        if evs is None:  # niet op tijd klaar: items van de vorige keer aanhouden
            vid = slug(src["name"] + "-" + src.get("city", "")) + ("-film" if src.get("type") == "film" else "")
            for e in prev_events:
                if e.get("v") == vid:
                    e = {k: v for k, v in e.items() if k not in ("v", "first_seen")}
                    events[e["id"]] = dict(e, venue=src["name"], city=src.get("city", ""), prov=src.get("prov", ""),
                                           vtype=src.get("type", "pop"), kind=src.get("type", "pop"))
            continue
        for ev in evs:
            # Zelfde voorstelling via twee bronnen (bv. dubbel in de lijst): één keer tonen
            key = (ev["url"].split("?")[0].rstrip("/"), ev["date"], ev.get("time"))
            if key in seen:
                continue
            seen.add(key)
            e = dict(ev, venue=src["name"], city=src.get("city", ""), prov=src.get("prov", ""),
                     vtype=src.get("type", "pop"), kind=src.get("type", "pop"))
            screening = e.pop("screening", False)
            e["genre"] = "Film" if is_film(e["title"], e["url"], e["vtype"], screening) \
                else src.get("genre") or guess_genre(e["title"], e["vtype"])
            # Films draaien meerdere keren per dag: tijd hoort dan bij de id
            # Lopende tentoonstelling zonder bekende begindatum: id op de einddatum, anders is hij elke dag 'nieuw'
            when = f"t/m {e['end']}" if e.pop("ongoing", False) and e.get("end") else e["date"]
            idkey = f"{src['name']}|{when}|{e['title']}" + (f"|{e['time']}" if e["vtype"] == "film" else "")
            e["id"] = "s" + hashlib.sha1(idkey.encode()).hexdigest()[:10]
            if tidy(e):  # na de id, zodat bestaande items hun id (favoriet, 'nieuw') houden
                events[e["id"]] = e
    fix_series_ends(events.values())
    return dedupe(relocate(events))


def relocate(events):
    """Een podium zet ook shows van andere podia in zijn agenda (013: 'Locatie | Hall of Fame').
    Staat die andere locatie als eigen bron in dezelfde stad, dan hoort de show daar: heeft dat podium hem zelf
    ook, dan gaat de kopie weg; anders verhuist hij naar dat podium."""
    key = lambda s: re.sub(r"[^a-z0-9]", "", unescape(s).lower())
    by_city = {}
    for s in json.loads(sources.BRONNEN.read_text(encoding="utf-8")):
        if s.get("enabled", True) and s.get("type") != "film":
            by_city.setdefault(key(s.get("city", "")), []).append(s)
    own = {(e["venue"], e["date"], norm(e["title"])) for e in events.values()}
    out = {}
    for k, e in events.items():
        loc = key(e.pop("loc", "") or "")
        if len(loc) >= 4 and e.get("vtype") not in ("film", "festival"):
            for s in by_city.get(key(e.get("city", "")), []):
                name = re.sub(r"\(.*?\)", "", s["name"])  # "Willem Twee Poppodium (W2)" -> "Willem Twee Poppodium"
                nk = key(name)
                if s["name"] == e["venue"] or len(nk) < 4 or not (nk in loc or loc in nk):
                    continue
                if (s["name"], e["date"], norm(e["title"])) in own:
                    e = None  # dat podium heeft de show zelf al
                else:
                    e.update(venue=s["name"], prov=s.get("prov", e["prov"]), vtype=s.get("type", e["vtype"]))
                break
        if e is not None:
            out[k] = e
    return out


# ---------------------------------------------------------------- opschonen (zie ook --reclassify)

CATEGORY_WORDS = {"musical", "tribute", "te gast", "jeugd en familie", "familie", "agenda", "programma", "program", "overzicht", "totaal overzicht", "randprogramma", "professioneel programma",
                  "laatste kaarten", "cabaret", "comedy", "stand-up comedy", "cabaret & comedy", "film", "films", "muziek",
                  "theater", "dans", "jeugd", "concerten", "voorstellingen", "home", "isala film"}
SERVICE_RE = re.compile(r"hulp bij digitale|digitale vragen|boekstart|steunpunt|is closed|is gesloten|gesloten van", re.I)


def tidy(e):
    """Titel (ook dubbel gecodeerd: "Cato &#038; Anton"), tijd en periode opschonen. Geeft False als het geen echte voorstelling is (kopje, bestelpagina, dienst)."""
    t = re.sub(r"<[^>]+>", " — ", unescape(unescape(e["title"])))                       # "Geert Mak <br>met ..." 
    t = re.sub(r"\s+tickets? kopen\?.*$", "", t, flags=re.I)       # Gebouw-T: "... tickets kopen? Bekijk snel de site"
    if re.search(r"\*\s*uitverkocht\s*\*", t, re.I):
        e["status"] = "sold"
        t = re.sub(r"\s*\*\s*uitverkocht\s*\*", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" —-")
    # "FamilieFest: Dwarsliggers FamilieFest: Dwarsl iggers": titel twee keer achter elkaar (afgekapt)
    for i in range(12, len(t) - 11):
        if t[i] == " " and t[i + 1:i + 13] == t[:12] and 0.35 < i / len(t) < 0.65:
            t = t[:i].strip()
            break
    e["title"] = t
    # Exposities bij theaters en podia (Chassé, Tolhuistuin, De Doelen...): genre Tentoonstelling, de app zet ze bij Musea
    if e.get("vtype") in ("pop", "concert", "arena", "cafe", "thea") and e.get("genre") != "Film" and \
            re.search(r"\bexpo\b|expositie|exposities|exposeert|tentoonstelling|exhibition", t, re.I):
        e["genre"] = "Tentoonstelling"
    slug_ = e["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1].lower()
    low = t.lower()
    flat = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    if (low in CATEGORY_WORDS or re.fullmatch(r"\d{1,2} ?plus|\d{1,2}\+", low)) and \
            (flat(low) == flat(slug_) or e["vtype"] == "film" or low in ("home", "agenda", "programma", "program",
                                                                          "totaal overzicht", "randprogramma")):
        return False                                                    # categorie- of overzichtspagina (Orpheus: /cabaret_comedy, /4plus)
    # Titel is de naam van het podium (Ledeltheater, Jazz Podium Goirle): de echte titel staat dan in de link
    venue = e.get("venue") or ""
    if venue and e.get("vtype") not in ("festival", "museum") and flat(t) == flat(venue):
        rest = re.sub("^" + re.escape(slug(venue)) + "-?", "", re.sub(r"-\d+$", "", slug_.strip("/")))
        if len(rest) < 3:
            return False
        e["title"] = t = rest.replace("-", " ").capitalize()
        low = t.lower()
    if re.match(r"agenda van \w+$|professioneel programma$|laatste kaarten$", low) or SERVICE_RE.search(t):
        return False
    # Tijden als 06:20 of 03:10 komen uit rommel op de pagina, niet van de voorstelling
    if e.get("time") and e["vtype"] != "film" and e["time"] < "09:00" and \
            (int(e["time"][3:]) % 15 or e["vtype"] == "museum" or "03:00" <= e["time"] < "06:00"):
        e["time"] = None
    if night_show(e):
        e.pop("end")
    # Bij een podium is een 'periode' van meer dan een maand een reeks of het seizoen, geen doorlopend evenement
    if e.get("end") and e["vtype"] in ("pop", "concert", "arena", "cafe", "thea") and \
            (dt.date.fromisoformat(e["end"]) - dt.date.fromisoformat(e["date"])).days > 31 and \
            not re.search(r"expo|tentoonstelling|winter efteling", t, re.I):
        e.pop("end")
    return True


def fix_series_ends(events):
    """Dezelfde einddatum bij 3+ verschillende items van één podium is een datum van de pagina (seizoen, week), geen eind."""
    groups = {}
    for e in events:
        if e.get("end") and e.get("vtype", "pop") not in ("festival", "museum"):
            groups.setdefault((e.get("venue") or e.get("v"), e["end"]), []).append(e)
    for evs in groups.values():
        if len({e["date"] for e in evs}) >= 3:
            for e in evs:
                e.pop("end")


def dedupe(events):
    """Zelfde podium, dag, tijd en titel (via twee links): één keer tonen."""
    out, seen = {}, set()
    for k, e in events.items():
        key = (e.get("venue") or e.get("v"), e["date"], e.get("time"), re.sub(r"\W", "", e["title"].lower()))
        if e.get("vtype") == "film" or key not in seen:
            seen.add(key)
            out[k] = e
    return out


def night_show(e):
    """Avondconcert dat 'tot de volgende dag' loopt (eindtijd middernacht, bv. SPOT Groningen) is geen tweedaags evenement."""
    if not e.get("end") or e["vtype"] in ("festival", "museum") or (e.get("time") or "") < "17:00":
        return False
    return (dt.date.fromisoformat(e["end"]) - dt.date.fromisoformat(e["date"])).days == 1


def reclassify():
    """Genres in de bestaande data.json opnieuw bepalen, zonder de bronnen opnieuw op te halen."""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    changed = 0
    keep = []
    for e in data["events"]:
        vtype = data["venues"].get(e["v"], {}).get("type", "pop")
        before = json.dumps(e, sort_keys=True)
        e["vtype"], e["venue"] = vtype, data["venues"].get(e["v"], {}).get("name", "")
        ok = tidy(e)
        e.pop("vtype"), e.pop("venue")
        if not ok:
            print(f"  {'weg':>12}    {e['title'][:70]}")
            changed += 1
            continue
        if json.dumps(e, sort_keys=True) != before:
            changed += 1
        keep.append(e)
    for e in keep:
        e["vtype"] = data["venues"].get(e["v"], {}).get("type", "pop")
    fix_series_ends(keep)
    n0 = len(keep)
    keep = list(dedupe({e["id"]: e for e in keep}).values())
    for e in keep:
        e.pop("vtype")
    changed += n0 - len(keep)
    data["events"] = keep
    for e in data["events"]:
        vtype = data["venues"].get(e["v"], {}).get("type", "pop")
        # Alleen films erbij zoeken: of de site zelf 'filmvertoning' zei, weten we hier niet meer
        g = "Film" if is_film(e["title"], e["url"], vtype) else \
            (guess_genre(e["title"], vtype) if e["genre"] == "Film" and LIVE_MUSIC_RE.search(e["title"]) else e["genre"])
        if g != e["genre"]:
            print(f"  {e['genre']:>12} -> {g:<12} {e['title'][:70]}")
            e["genre"], changed = g, changed + 1
    V = data["venues"]
    before = {id(e): e["genre"] for e in data["events"]}
    mark_known_films([(e, V.get(e["v"], {}).get("name"), V.get(e["v"], {}).get("type", "pop")) for e in data["events"]])
    for e in data["events"]:
        if e["genre"] != before[id(e)]:
            print(f"  {before[id(e)]:>12} -> {'Film':<12} {e['title'][:70]} (titel uit filmagenda)")
            changed += 1
    print(f"{changed} genres aangepast")
    if not ARGS.dry_run:
        OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    if ARGS.reclassify:
        return reclassify()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"events": []}
    first_seen = {e["id"]: e.get("first_seen", TODAY.isoformat()) for e in prev.get("events", [])}

    events = own_events(prev.get("events", []))
    print(f"Eigen bronnen: {len(events)} items")
    n = mark_known_films([(e, e["venue"], e["vtype"]) for e in events.values()])
    print(f"Films herkend aan een titel uit de filmagenda: {n}")
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
    hz_film = (TODAY + dt.timedelta(days=CFG.get("film_days_ahead", 10))).isoformat()  # draaitijden: alleen komende dagen
    events = {k: v for k, v in events.items() if (v.get("end") or v["date"]) >= t0
              and v["date"] <= {"festival": hz_long, "museum": hz_long, "film": hz_film}.get(v["vtype"], hz)}

    cache = json.loads(VCACHE.read_text(encoding="utf-8")) if VCACHE.exists() else {}
    venues, budget = {}, CFG["geocode_max_per_run"]
    for e in events.values():
        city = e["city"] or ""
        # Eigen id voor de filmzaal van een podium dat ook als poppodium/theater in de lijst staat (bv. De Cacaofabriek),
        # anders belanden de concerten in het tabblad Film of de films bij Muziek
        vid = slug(e["venue"] + "-" + city) + ("-film" if e["vtype"] == "film" else "")
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
        if ARGS.source:  # één bron testen: alles tonen, één regel per item
            for e in out["events"]:
                print(f"  {e['date']} {e.get('end') or '':10} {e['time'] or '--:--'} {e.get('status') or '':9} {e['genre']:10} "
                      f"{e['title'][:60]} | {e['url']}"
                      + "".join(f" | {k}={e[k]}" for k in ("doors", "start", "support", "times") if e.get(k)))
        else:
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
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    sys.stdout.flush()
    # Niet wachten op bronnen die na de tijdslimiet nog bezig zijn
    os._exit(code)
