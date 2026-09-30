"""Eigen bronnen: leest de agenda rechtstreeks van de sites van podia, theaters, musea en festivals.

Werkwijze per bron (scraper/bronnen.json):
  1. Haal de agendapagina op (plus eventuele vervolgpagina's).
  2. Pak schema.org-events (JSON-LD) die al op die pagina staan.
  3. Verzamel links naar losse voorstellingspagina's op dezelfde site en haal die op
     (met cache, zodat elke nacht alleen nieuwe pagina's echt worden opgehaald).
  4. Lukt JSON-LD niet, dan zoeken we datum en tijd in de tekst van de pagina.
Elke site krijgt hoogstens één verzoek per `delay_seconds`; verschillende sites lopen parallel.
"""
import datetime as dt, json, pathlib, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib import robotparser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRONNEN = ROOT / "scraper/bronnen.json"
CACHE = ROOT / "scraper/detail_cache.json"
TODAY = dt.date.today()

DETAIL_RE = re.compile(r"/(agenda|programma|programme|event|events|evenement|evenementen|concert|concerten|"
                       r"voorstelling|voorstellingen|show|shows|tentoonstelling|tentoonstellingen|exhibition|"
                       r"exhibitions|activiteit|activiteiten|nu-te-zien|productie|producties)/[^?#]{3,}", re.I)
SKIP_RE = re.compile(r"\.(jpe?g|png|gif|svg|pdf|ics|zip|mp[34])$|/(tag|categor(y|ie)|genre|page|zoeken|search|"
                     r"filter|nieuws|news|login|account|winkelwagen|cart)/|[?&](page|filter|genre)=", re.I)

MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}
TXT_DATE_RE = re.compile(r"\b(\d{1,2})\s+(jan|feb|mrt|maa|mar|apr|mei|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.?"
                         r"(?:\s+'?(\d{4}|\d{2}))?\b", re.I)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:uur|u\b)?", re.I)


# ---------------------------------------------------------------- ophalen

class Fetcher:
    """Beleefd ophalen: robots.txt per site, vaste pauze per site, eigen User-Agent."""

    def __init__(self, ua, delay):
        self.S = requests.Session()
        self.S.headers.update({"User-Agent": ua, "Accept-Language": "nl,en;q=0.5"})
        self.ua, self.delay = ua, delay
        self.robots, self.last, self.locks = {}, {}, {}
        self.guard = threading.Lock()

    def _host(self, url):
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        with self.guard:
            if host not in self.locks:
                self.locks[host] = threading.Lock()
        return host

    def allowed(self, url):
        host = self._host(url)
        if host not in self.robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.S.get(host + "/robots.txt", timeout=20)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[host] = rp
        return self.robots[host].can_fetch(self.ua, url)

    def get(self, url):
        host = self._host(url)
        with self.locks[host]:
            if not self.allowed(url):
                return None
            wait = self.delay - (time.time() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.time()
            try:
                r = self.S.get(url, timeout=30)
            except requests.RequestException:
                return None
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
            return None
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        return r.text


# ---------------------------------------------------------------- uitlezen

def _walk_events(o, out):
    if isinstance(o, dict):
        t = o.get("@type")
        ts = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and (x.endswith("Event") or x in ("Festival", "ExhibitionEvent")) for x in ts):
            out.append(o)
        for v in o.values():
            _walk_events(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_events(v, out)


def jsonld_events(soup):
    out = []
    for s in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        txt = (s.string or s.get_text() or "").strip()
        if not txt:
            continue
        try:
            _walk_events(json.loads(txt), out)
        except ValueError:
            # Sommige sites zetten losse objecten achter elkaar of laten een komma staan.
            try:
                _walk_events(json.loads("[" + re.sub(r"}\s*{", "},{", txt).rstrip(",") + "]"), out)
            except ValueError:
                pass
    return out


def _iso(s):
    """'2026-10-01T20:15:00+00:00' -> (date, '20:15'). We nemen de kloktijd zoals de site hem noemt:
    veel sites plakken er ten onrechte +00:00 achter terwijl het Nederlandse tijd is."""
    if not isinstance(s, str):
        return None, None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", s.strip())
    if not m:
        return None, None
    try:
        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None, None
    t = f"{m.group(4)}:{m.group(5)}" if m.group(4) and (m.group(4), m.group(5)) != ("00", "00") else None
    return d, t


def _name(x):
    if isinstance(x, list):
        return ", ".join(filter(None, (_name(i) for i in x)))
    if isinstance(x, dict):
        return (x.get("name") or "").strip()
    return (x or "").strip() if isinstance(x, str) else ""


def from_jsonld(o, page_url):
    d, t = _iso(o.get("startDate"))
    if not d:
        return None
    end, end_t = _iso(o.get("endDate"))
    if end and end_t and end_t < "08:00" and (end - d).days == 1:
        end = None  # nachtprogramma, geen meerdaags evenement
    title = unescape(_name(o.get("name")) or "").strip()
    if not title:
        return None
    ev = {"date": d.isoformat(), "time": t, "title": title,
          "url": o.get("url") if isinstance(o.get("url"), str) and o["url"].startswith("http") else page_url}
    if end and end > d:
        ev["end"] = end.isoformat()
    perf = [p for p in re.split(r"\s*,\s*", _name(o.get("performer"))) if p and p.lower() != title.lower()]
    if len(perf) > 1:
        ev["support"] = perf[1:4]
    status = json.dumps([o.get("eventStatus"), o.get("offers")]).lower()
    if "soldout" in status or "uitverkocht" in status:
        ev["status"] = "sold"
    elif "cancel" in status or "postponed" in status:
        ev["status"] = "cancelled"
    return ev


def _txt_date(txt):
    """Eerste datum in de tekst; jaar weggelaten = eerstvolgende keer dat die datum valt."""
    best = None
    for m in NUM_DATE_RE.finditer(txt):
        try:
            best = (m.start(), dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            continue
        break
    for m in TXT_DATE_RE.finditer(txt):
        if best and m.start() > best[0]:
            break
        mon = MONTHS[m.group(2).lower()[:3]]
        yy = m.group(3)
        y = (2000 + int(yy) if len(yy) == 2 else int(yy)) if yy else TODAY.year
        try:
            d = dt.date(y, mon, int(m.group(1)))
        except ValueError:
            continue
        if not yy and d < TODAY - dt.timedelta(days=60):
            d = d.replace(year=y + 1)
        best = (m.start(), d)
        break
    return best[1] if best else None


def from_text(soup, url):
    """Terugval als er geen bruikbare JSON-LD is: titel uit og:title/h1, datum en tijd uit de tekst."""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    for bad in main.find_all(["nav", "footer", "header", "script", "style", "form"]):
        bad.decompose()
    txt = main.get_text("\n", strip=True)[:6000]
    h1 = soup.find("h1")
    og = soup.find("meta", property="og:title")
    title = (h1.get_text(" ", strip=True) if h1 else "") or (og.get("content", "") if og else "")
    title = re.split(r"\s+[|–—-]\s+(?=[^|–—-]*$)", title)[0].strip() if "|" in title else title.strip()
    d = _txt_date(txt)
    end = None
    # Periode, bv. "12 sep 2026 t/m 10 jan 2027" of "nog t/m 10 januari 2027" (tentoonstellingen, festivals)
    m = re.search(r"(?:t/m|tot en met|tot|until|[–—-])\s*(\d{1,2}\s+[a-z]{3,}\.?(?:\s+\d{4})?|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})",
                  txt, re.I)
    if m:
        end = _txt_date(m.group(1))
        if end and d and end < d:
            end = end.replace(year=end.year + 1) if (d - end).days < 330 else None
        if end and not d:
            d = TODAY
    if not title or not d:
        return None

    def grab(pat):
        m = re.search(pat + r"\D{0,25}?\b([01]?\d|2[0-3])[:.]([0-5]\d)", txt, re.I)
        return f"{int(m.group(2)):02d}:{m.group(3)}" if m else None

    doors = grab(r"(deuren open|zaal open|deur open|doors)")
    start = grab(r"(aanvang|start|begint|showtime|begintijd)")
    t = start or doors
    if not t:
        m = TIME_RE.search(txt)
        t = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    ev = {"date": d.isoformat(), "time": t, "title": title, "url": url}
    if end and (end - d).days >= 1:
        ev["end"] = end.isoformat()
    if doors:
        ev["doors"] = doors
    if start:
        ev["start"] = start
    if re.search(r"\buitverkocht\b|\bsold ?out\b", txt, re.I):
        ev["status"] = "sold"
    return ev


def detail_links(soup, page_url, pattern=None):
    host = urlparse(page_url).netloc.removeprefix("www.")
    rx = re.compile(pattern, re.I) if pattern else DETAIL_RE
    base = page_url.split("#")[0].rstrip("/")
    seen = []
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"]).split("#")[0]
        p = urlparse(u)
        if p.netloc.removeprefix("www.") != host or u.rstrip("/") == base or SKIP_RE.search(u):
            continue
        if rx.search(p.path) and u not in seen:
            seen.append(u)
    return seen


def next_pages(soup, page_url, html):
    out = []
    ln = soup.find("link", rel="next") or soup.find("a", rel="next")
    if ln and ln.get("href"):
        out.append(urljoin(page_url, ln["href"]))
    return out


MON = r"(jan|feb|mrt|maa|mar|apr|mei|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.?"
# "12, 13 & 14 juni 2027", "5 t/m 7 juni", "24-26 juli 2026", "vr 3 - zo 5 juli"
FEST_RE = re.compile(r"\b(\d{1,2})(?:\s*(?:[-–—/&,]|t/m|tot en met|en|and)\s*(?:[a-z]{2,9}\.?\s+)?(\d{1,2}))*\s+"
                     + MON + r"(?:\s+'?(\d{4}|\d{2}))?\b", re.I)
# "30 mei - 1 juni 2027"
FEST2_RE = re.compile(r"\b(\d{1,2})\s+" + MON + r"(?:\s+(\d{4}))?\s*(?:[-–—]|t/m|tot en met)\s*(?:[a-z]{2,9}\.?\s+)?"
                      r"(\d{1,2})\s+" + MON + r"(?:\s+(\d{4}))?", re.I)


def festival_event(src, F, log):
    """Eén item per festival: naam + periode, gelezen van de festivalsite (JSON-LD of tekst)."""
    html = F.get(src["agenda_url"])
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    evs = [e for e in (from_jsonld(o, src["agenda_url"]) for o in jsonld_events(soup)) if e]
    evs = sorted((e for e in evs if (e.get("end") or e["date"]) >= TODAY.isoformat()), key=lambda e: e["date"])
    if evs:
        d0, d1 = evs[0]["date"], max(e.get("end") or e["date"] for e in evs)
    else:
        for bad in soup.find_all(["script", "style", "noscript"]):
            bad.decompose()
        head = " ".join(filter(None, [(soup.find("meta", attrs={"name": "description"}) or {}).get("content"),
                                      (soup.find("meta", property="og:description") or {}).get("content"),
                                      soup.get_text(" ", strip=True)[:8000]]))

        def mk(day, mon, yy):
            m = MONTHS[mon.lower()[:3]]
            y = (2000 + int(yy) if yy and len(yy) == 2 else int(yy)) if yy else TODAY.year
            d = dt.date(y, m, int(day))
            return d.replace(year=y + 1) if not yy and d < TODAY - dt.timedelta(days=7) else d

        found = None
        for m in FEST2_RE.finditer(head):
            try:
                a = mk(m.group(1), m.group(2), m.group(3) or m.group(6))
                b = mk(m.group(4), m.group(5), m.group(6))
            except ValueError:
                continue
            if a <= b and (b - a).days < 45 and b >= TODAY:
                found = (a, b)
                break
        if not found:
            for m in FEST_RE.finditer(head):
                try:
                    a = mk(m.group(1), m.group(3), m.group(4))
                    b = mk(m.group(2), m.group(3), m.group(4)) if m.group(2) else a
                except ValueError:
                    continue
                if a <= b and (b - a).days < 45 and b >= TODAY and a.year <= TODAY.year + 1:
                    found = (a, b)
                    break
        if not found:
            log(f"  {src['name']}: geen festivaldatum gevonden")
            return []
        d0, d1 = found[0].isoformat(), found[1].isoformat()
    ev = {"date": d0, "time": None, "title": src["name"], "url": src["agenda_url"]}
    if d1 > d0:
        ev["end"] = d1
    log(f"  {src['name']}: {d0} t/m {d1}")
    return [ev]


# ---------------------------------------------------------------- per bron

def scrape_source(src, F, cache, cfg, log):
    if src.get("type") == "festival" and src.get("mode") != "agenda":
        return festival_event(src, F, log)
    events, pages = {}, [src["agenda_url"]] + src.get("extra_urls", [])
    seen_pages, links = set(), []
    max_pages = src.get("max_pages", cfg.get("source_max_pages", 8))
    while pages and len(seen_pages) < max_pages:
        url = pages.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        html = F.get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for o in jsonld_events(soup):
            ev = from_jsonld(o, url)
            if ev:
                events.setdefault((ev["date"], ev["title"].lower()), ev)
        for u in detail_links(soup, url, src.get("link_pattern")):
            if u not in links:
                links.append(u)
        pages += [p for p in next_pages(soup, url, html) if p not in seen_pages]

    known = {e["url"] for e in events.values()}
    fresh = (TODAY - dt.timedelta(days=cfg.get("detail_refresh_days", 7))).isoformat()
    fetched = 0
    for u in links[:src.get("max_details", cfg.get("source_max_details", 250))]:
        if u in known:
            continue
        c = cache.get(u)
        # Opnieuw ophalen als de cache oud is, of als de voorstelling binnen twee weken is (tijden/uitverkocht).
        soon = c and c.get("ev") and c["ev"]["date"] <= (TODAY + dt.timedelta(days=14)).isoformat()
        if c and c.get("at", "") >= fresh and not (soon and c.get("at") != TODAY.isoformat()):
            evs = [c["ev"]] if c.get("ev") else []
        else:
            html = F.get(u)
            fetched += 1
            evs = []
            if html:
                soup = BeautifulSoup(html, "html.parser")
                evs = [e for e in (from_jsonld(o, u) for o in jsonld_events(soup)) if e]
                if not evs:
                    e = from_text(soup, u)
                    evs = [e] if e else []
            cache[u] = {"at": TODAY.isoformat(), "ev": evs[0] if len(evs) == 1 else None}
            if len(evs) > 1:
                cache[u]["evs"] = evs
            elif not evs:
                cache[u]["ev"] = None
        if c and c.get("evs"):
            evs = c["evs"]
        for ev in evs:
            events.setdefault((ev["date"], ev["title"].lower()), ev)
    log(f"  {src['name']}: {len(events)} items ({len(links)} links, {fetched} opgehaald)")
    return list(events.values())


def collect(cfg, only=None, log=print):
    """Geeft [(bron, [events])] terug voor alle bronnen in bronnen.json."""
    if not BRONNEN.exists():
        return []
    srcs = [s for s in json.loads(BRONNEN.read_text(encoding="utf-8"))
            if s.get("agenda_url") and s.get("enabled", True) and (not only or only.lower() in s["name"].lower())]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    F = Fetcher(cfg["user_agent"], cfg["delay_seconds"])
    lock = threading.Lock()

    def one(src):
        local = {}
        with lock:
            local.update({k: v for k, v in cache.items()})
        try:
            evs = scrape_source(src, F, local, cfg, log)
        except Exception as e:  # een kapotte site mag de rest niet tegenhouden
            log(f"  {src['name']}: fout {e.__class__.__name__}: {e}")
            evs = []
        with lock:
            cache.update({k: v for k, v in local.items() if k not in cache or v is not cache.get(k)})
        return src, evs

    with ThreadPoolExecutor(max_workers=cfg.get("source_workers", 12)) as pool:
        results = list(pool.map(one, srcs))
    horizon = (TODAY - dt.timedelta(days=cfg.get("cache_keep_days", 30))).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("at", "") >= horizon}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return results
