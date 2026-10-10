"""Eigen bronnen: leest de agenda rechtstreeks van de sites van podia, theaters, musea en festivals.

Werkwijze per bron (scraper/bronnen.json):
  1. Haal de agendapagina op (plus eventuele vervolgpagina's).
  2. Pak schema.org-events (JSON-LD) die al op die pagina staan.
  3. Verzamel links naar losse voorstellingspagina's op dezelfde site en haal die op
     (met cache, zodat elke nacht alleen nieuwe pagina's echt worden opgehaald).
  4. Lukt JSON-LD niet, dan zoeken we datum en tijd in de tekst van de pagina.
Elke site krijgt hoogstens één verzoek per `delay_seconds`; verschillende sites lopen parallel.
"""
import datetime as dt, json, pathlib, re, socket, threading, time
from concurrent.futures import ThreadPoolExecutor, wait
from html import escape, unescape
from urllib import robotparser
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import film
import museum
import prijzen
import venues

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRONNEN = ROOT / "scraper/bronnen.json"
CACHE = ROOT / "scraper/detail_cache.json"
REPORT = ROOT / "scraper/rapport.json"
LOKAAL = ROOT / "scraper/lokaal.json"          # geschreven door scraper/lokaal.py op de eigen computer van de eigenaar
LOCAL_CACHE = ROOT / "scraper/lokaal_cache.json"  # aparte cache, zodat die niet botst met de cache van GitHub
TODAY = dt.date.today()
CACHE_V = 4  # ophogen als het uitlezen verandert, zodat gecachte pagina's opnieuw worden gelezen

DETAIL_RE = re.compile(r"/(agenda|programma|programme|event|events|evenement|evenementen|concert|concerten|film|films|movies?|"
                       r"voorstelling|voorstellingen|show|shows|tentoonstelling|tentoonstellingen|exhibition|"
                       r"exhibitions|activiteit|activiteiten|nu-te-zien|productie|producties)/[^?#]{3,}", re.I)
SKIP_RE = re.compile(r"\.(jpe?g|png|gif|svg|pdf|ics|zip|mp[34])$|/(order|bestellen|checkout|winkelmand|basket)/|"
                     r"/(tag|categor(y|ie)|genre|page|zoeken|search|"
                     r"filter|nieuws|news|login|account|winkelwagen|cart)/|[?&](page|filter|genre)=", re.I)

MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}
# Alleen echte maandnamen met woordgrens: anders is "05 Maassilo" 5 maart en "12 Junior" 12 juni
TXT_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(jan(?:uari|uary)?|feb(?:ruari|ruary)?|mrt|maart|mar(?:ch)?|apr(?:il)?|mei|may|jun[ie]?|jul[iy]?|"
    r"aug(?:ustus|ust)?|sep(?:t(?:ember)?)?|okt(?:ober)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\b"
    # jaartal: "3 okt 12:40" en "3 okt 19 uur" zijn geen jaartal; "12 november , 2026" wel
    r"(?:\s*,?\s+'?(\d{4}|\d{2})(?![:.]\d)(?!\s*u(?:ur)?\b))?\b", re.I)
# Engels met de maand vóór de dag: "Thursday - October 15th", "October 15, 2026" (Fontys). 'May' alleen met hoofdletter.
EN_DATE_RE = re.compile(r"\b((?-i:May)|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?![:.]\d)(?:,?\s+(20\d\d))?", re.I)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?![.\-/]\d)\s*(?:uur|u\b)?", re.I)  # "03.10.2026" is geen 03:10


# ---------------------------------------------------------------- ophalen

class Fetcher:
    """Beleefd ophalen: robots.txt per site, vaste pauze per site, eigen User-Agent."""

    def __init__(self, ua, delay):
        self.S = requests.Session()
        self.S.max_redirects = 5
        self.S.headers.update({"User-Agent": ua, "Accept-Language": "nl,en;q=0.5"})
        self.ua, self.delay = ua, delay
        self.robots, self.last, self.locks, self.ip_locks, self.host_ip = {}, {}, {}, {}, {}
        self.stats = {}  # per site: hoe vaak welke antwoordcode (voor scraper/rapport.json)
        self.guard = threading.Lock()

    def _host(self, url):
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        with self.guard:
            if host not in self.locks:
                # Veel filmhuizen/theaters delen één server: de pauze geldt per server (IP), niet per sitenaam
                try:
                    ip = socket.gethostbyname(p.hostname or "")
                except OSError:
                    ip = host
                if ip not in self.ip_locks:
                    self.ip_locks[ip] = threading.Lock()
                self.locks[host] = self.ip_locks[ip]
                self.host_ip[host] = ip
        return host

    def allowed(self, url):
        host = self._host(url)
        if host not in self.robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.S.get(host + "/robots.txt", timeout=20)
                # Een BOM aan het begin maakt de eerste regel ("User-agent: *") onleesbaar voor robotparser,
                # die dan alles toestaat. Weghalen, zodat een verbod ook echt een verbod is.
                rp.parse(r.content.decode("utf-8-sig", errors="replace").splitlines() if r.status_code == 200 else [])
                if r.status_code >= 500:
                    rp.disallow_all = True  # server-fout: voor de zekerheid niets ophalen
            except requests.RequestException:
                rp.parse([])
            self.robots[host] = rp
        return self.robots[host].can_fetch(self.ua, url)

    def _note(self, host, what):
        with self.guard:
            st = self.stats.setdefault(urlparse(host).netloc.removeprefix("www."), {})
            st[what] = st.get(what, 0) + 1

    def _fetch(self, url, params=None, json_body=None, headers=None):
        host = self._host(url)
        with self.locks[host]:
            if not self.allowed(url):
                self._note(host, "robots")
                return None
            # Vraagt de site in robots.txt om meer tijd tussen verzoeken, dan houden we ons daaraan (max 10 s)
            delay = max(self.delay, min(10, self.robots[host].crawl_delay(self.ua) or 0))
            ip = self.host_ip[host]
            wait = delay - (time.time() - self.last.get(ip, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[ip] = time.time()
            try:
                r = self.S.post(url, json=json_body, headers=headers, timeout=30, stream=True) if json_body is not None \
                    else self.S.get(url, params=params, timeout=30, stream=True)
                if not self._lees(r):   # te groot of te traag: niet meer verwerken
                    self._note(host, "te groot of te traag")
                    return None
            except requests.RequestException as e:
                self._note(host, "timeout" if isinstance(e, requests.Timeout) else "verbindingsfout")
                return None
        self._note(host, str(r.status_code))
        return r if r.status_code == 200 else None

    MAX_BYTES = 25_000_000   # een agendapagina of API-antwoord groter dan dit lezen we niet
    MAX_SECONDEN = 90        # en wat langer dan dit blijft druppelen ook niet

    def _lees(self, r):
        """Leest het antwoord (met een bovengrens voor grootte en tijd) en zet het in r.content; False als het niet lukt."""
        try:
            if int(r.headers.get("content-length") or 0) > self.MAX_BYTES:
                r.close(); return False
        except ValueError:
            pass
        t0, delen, n = time.time(), [], 0
        for chunk in r.iter_content(65536):
            n += len(chunk)
            if n > self.MAX_BYTES or time.time() - t0 > self.MAX_SECONDEN:
                r.close(); return False
            delen.append(chunk)
        r._content, r._content_consumed = b"".join(delen), True
        return True

    def get(self, url):
        r = self._fetch(url)
        if r is None or "html" not in r.headers.get("content-type", "html"):
            return None
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        return r.text

    def get_json(self, url, params=None):
        r = self._fetch(url, params)
        try:
            return r.json() if r is not None else None
        except ValueError:
            return None

    def get_text(self, url):
        """Ruwe tekst (bv. een JavaScript-bestand), zonder de html-controle van get()."""
        r = self._fetch(url)
        return r.text if r is not None else None

    def post_json(self, url, body, headers=None):
        """POST met JSON (sommige sites halen hun agenda zo op); zelfde pauze en robots-regels als get."""
        r = self._fetch(url, json_body=body, headers=headers)
        try:
            return r.json() if r is not None else None
        except ValueError:
            return None


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
    veel sites plakken er ten onrechte +00:00 achter terwijl het Nederlandse tijd is.
    Alleen een expliciete 'Z' (bv. '2026-10-01T18:00:00Z') is echt UTC en rekenen we om naar Nederlandse tijd."""
    if not isinstance(s, str):
        return None, None
    s = s.strip()
    mz = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2})?(?:\.\d+)?Z$", s)
    if mz:
        x = dt.datetime.fromisoformat(f"{mz.group(1)}T{mz.group(2)}+00:00").astimezone(museum.NL)
        return x.date(), (x.strftime("%H:%M") if x.strftime("%H:%M") != "00:00" else None)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", s)
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
    if not d or d.year < 2000:  # kapotte JSON-LD (bv. 1970-01-01): dan liever de tekst lezen
        return None
    raw_end = o.get("endDate")
    end, end_t = _iso(raw_end)
    midnden = isinstance(raw_end, str) and "T00:00" in raw_end   # 'T00:00' = einde van de dag ervoor (_iso geeft dan geen tijd terug)
    if end and ((end_t and end_t < "08:00") or (midnden and t)) and (end - d).days == 1:
        end = None  # nachtprogramma of tot middernacht (Here's The Thing, 013): één dag, geen meerdaags evenement
    # Bij een filmvoorstelling (ScreeningEvent) is de film de titel, niet "Voorstelling 20:15"
    wp, nm = _name(o.get("workPresented")), _name(o.get("name"))
    title = unescape(wp if wp and not re.fullmatch(r"[\d\s#-]+", wp) else nm or wp or "").strip()
    if not title:
        return None
    ev = {"date": d.isoformat(), "time": t, "title": title,
          "url": o.get("url") if isinstance(o.get("url"), str) and o["url"].startswith("http") else page_url}
    if end and end > d:
        ev["end"] = end.isoformat()
    if "ScreeningEvent" in str(o.get("@type")):
        ev["screening"] = True  # de site zegt zelf dat het een filmvertoning is
    loc = _name(o.get("location"))
    if loc:
        ev["loc"] = loc  # waar het is; scrape.py zet een show bij het juiste podium als dat een ander podium is
    perf = [p for p in re.split(r"\s*,\s*", _name(o.get("performer"))) if p and p.lower() != title.lower()]
    if len(perf) > 1 and "Screening" not in str(o.get("@type")):  # bij films zijn dit acteurs
        ev["support"] = perf[1:4]
    price = prijzen.from_offers(o)  # laagste prijs in euro's, 0 = gratis; weg als onbekend
    if price is not None:
        ev["price"] = price
    status = json.dumps([o.get("eventStatus"), o.get("offers")]).lower()
    if "soldout" in status or "uitverkocht" in status:
        ev["status"] = "sold"
    # Afgelast alleen op eventStatus: in offers staat vaak iets als 'cancellationPolicy' of een annuleerlink,
    # en dan verdween de hele agenda (Neushoorn, okt 2026)
    elif re.search(r"cancel|postponed", str(o.get("eventStatus") or ""), re.I):
        ev["status"] = "cancelled"
    return ev


def _txt_date(txt):
    """Eerste datum in de tekst; jaar weggelaten = eerstvolgende keer dat die datum valt.
    Een datum direct achter het woord 'Datum' gaat voor (anders pakken we soms een datum uit de tekst)."""
    m = re.search(r"\bdatum\s*:?\s*", txt, re.I)
    if m and not txt.startswith("\x00"):
        d = _txt_date("\x00" + txt[m.end():m.end() + 40])
        if d:
            return d
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
    for m in EN_DATE_RE.finditer(txt):
        if best and m.start() > best[0]:
            break
        mon, yy = MONTHS[m.group(1).lower()[:3]], m.group(3)
        try:
            d = dt.date(int(yy) if yy else TODAY.year, mon, int(m.group(2)))
        except ValueError:
            continue
        if not yy and d < TODAY - dt.timedelta(days=60):
            d = d.replace(year=d.year + 1)
        best = (m.start(), d)
        break
    if not best:
        # "Datum 16-10" zonder jaartal (alleen direct na het woord datum, anders te veel valse treffers)
        m = re.search(r"(?:\bdatum\s*:?\s*|^\x00)(?:[a-z]{2,9}\.?\s+)?(\d{1,2})[-/.](\d{1,2})(?![-/.]?\d)", txt, re.I)
        if m:
            try:
                d = dt.date(TODAY.year, int(m.group(2)), int(m.group(1)))
                best = (m.start(), d.replace(year=d.year + 1) if d < TODAY - dt.timedelta(days=60) else d)
            except ValueError:
                pass
    return best[1] if best else None


GENERIC_TITLE = re.compile(r"^(agenda|programma|programme|overzicht|evenementen|events?|tickets?|kaarten|koop|nu te zien|"
                           r"tentoonstellingen?|voorstellingen?|concerten|films?|filmagenda|theateragenda|weekladder|"
                           r"specials?|archief|home|welkom|verwacht|binnenkort|\d+|\s|[^\w])+$", re.I)


def _slug_title(url):
    last = [p for p in urlparse(url).path.split("/") if p][-1:] or [""]
    s = re.sub(r"[-_]+", " ", re.sub(r"^\d+-|-\d+$|\.\w+$", "", last[0])).strip()
    return s[:1].upper() + s[1:]


def clean_title(t, site=""):
    t = unescape(t or "").strip()
    if site:
        t = re.sub(r"\s*[|–—:-]\s*" + re.escape(site) + r"\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*[|–—]\s*[^|–—]{2,40}$", "", t) if re.search(r"\s[|–—]\s", t) else t
    # "Spiritbox op 3 oktober 2026 naar AFAS Live!" -> "Spiritbox"
    t = re.sub(r"\s+(op|on|in|at|@)\s+(ma|di|wo|do|vr|za|zo|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)?\.?\s*"
               r"\d{1,2}[\s./-]+\w+[\s./-]+\d{2,4}\b.*$", "", t, flags=re.I)
    if site:
        t = re.sub(r"\s+(naar|in|bij|live in|@)\s+" + re.escape(site) + r".*$", "", t, flags=re.I)
    return t.strip(" -|!")


def pick_title(soup, url):
    """Titel van een voorstellingspagina: h1, tenzij dat een algemeen kopje is ('Agenda overzicht')."""
    site = (soup.find("meta", property="og:site_name") or {}).get("content", "")
    h1 = soup.find("h1")
    cands = [h1.get_text(" ", strip=True) if h1 else "",
             (soup.find("meta", property="og:title") or {}).get("content", ""),
             soup.title.get_text(" ", strip=True) if soup.title else ""]
    for c in cands:
        c = clean_title(c, site)
        if c and len(c) > 1 and not GENERIC_TITLE.match(c) and c.lower() != site.lower():
            return c
    return _slug_title(url)


OTHER_EVENTS_RE = re.compile(r"more-events|other-events|related|recommend|aanrader|ook-leuk|also-|news-box|nieuws|"
                             r"upcoming|carousel|swiper|slider", re.I)


def from_text(soup, url):
    """Terugval als er geen bruikbare JSON-LD is: titel uit og:title/h1, datum en tijd uit de tekst."""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    for bad in main.find_all(["nav", "footer", "header", "script", "style", "form"]):
        # Een <header> ín de voorstelling (Melkweg: datum en tijd staan daar) laten staan; alleen de sitekop weg
        if bad.name == "header" and main.name in ("main", "article"):
            continue
        bad.decompose()
    # Blokken met ándere voorstellingen ("meer concerten", nieuws, aanraders) geven anders de verkeerde datum
    # of 'uitverkocht' (PaRaDoX: rij 'more-events' met de eerstvolgende concerten)
    for bad in main.find_all(class_=OTHER_EVENTS_RE):
        if not bad.find("h1"):
            bad.decompose()
    # Verborgen tekst telt niet: Webflow (Neushoorn) zet 'Geannuleerd' op élke pagina, verborgen met
    # w-condition-invisible; anders gold elke show als afgelast (okt 2026)
    for bad in main.find_all(lambda t: "w-condition-invisible" in (t.get("class") or []) or t.has_attr("hidden")
                             or re.search(r"display\s*:\s*none", t.get("style") or "", re.I)):
        if not bad.decomposed:
            bad.decompose()
    txt = main.get_text("\n", strip=True)[:6000]
    title = pick_title(soup, url)
    d = _txt_date(txt)
    if d and d < TODAY - dt.timedelta(days=365):
        d = None  # datum van jaren terug ("opgericht in 2009", oude recensie): geen speeldatum
    if not d and main is not soup.body and soup.body:
        # Datum staat soms buiten <main>/<article> (lege article, datum in de paginakop)
        d = _txt_date(soup.body.get_text("\n", strip=True)[:6000])
        if d and d < TODAY - dt.timedelta(days=365):
            d = None
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
    start = grab(r"(aanvang|start|begint|showtime|begintijd|tijd\s*:)")
    t = start or doors
    if not t:
        m = TIME_RE.search(txt)
        t = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    ev = {"date": d.isoformat(), "time": t, "title": title, "url": url}
    if end and (end - d).days >= 1:
        ev["end"] = end.isoformat()
    # "Locatie | Hall of Fame" op de pagina van 013: de show is bij een ander podium
    m = re.search(r"\bLocatie\s*[:\n]?\s*\n?([^\n]{2,60})", txt)
    if m and not re.match(r"(en|&|\d|:)", m.group(1).strip()):
        ev["loc"] = m.group(1).strip()
    if doors:
        ev["doors"] = doors
    if start:
        ev["start"] = start
    price = prijzen.from_text(txt)  # laagste prijs in euro's, 0 = gratis; weg als onbekend
    if price is not None:
        ev["price"] = price
    if re.search(r"\buitverkocht\b|\bvolgeboekt\b|\bsold ?out\b", txt, re.I):
        ev["status"] = "sold"
    # Afgelast bovenaan de pagina (niet ergens in de tekst over een ander concert)
    if re.search(r"\b(afgelast|geannuleerd|gaat niet door|cancelled|canceled)\b", txt[:800], re.I):
        ev["status"] = "cancelled"
    return ev


def detail_links(soup, page_url, pattern=None, attrs=()):
    """Links naar voorstellingspagina's. attrs: extra attributen met een link (bv. data-target bij Grenswerk)."""
    host = urlparse(page_url).netloc.removeprefix("www.")
    rx = re.compile(pattern, re.I) if pattern else DETAIL_RE
    base = page_url.split("#")[0].rstrip("/")
    seen = []
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    for at in attrs:
        hrefs += [x[at] for x in soup.find_all(attrs={at: True})]
    # <base href="..."> bepaalt waar relatieve links naartoe wijzen (Boerderij: 'contact/' is /contact/, niet /programma/contact/)
    basis = urljoin(page_url, (soup.find("base", href=True) or {}).get("href") or page_url)
    for href in hrefs:
        u = urljoin(basis, href).split("#")[0]
        p = urlparse(u)
        if p.netloc.removeprefix("www.") != host or u.rstrip("/") == base or SKIP_RE.search(u):
            continue
        # Met een eigen link_pattern telt ook de vraag mee (Vera: /?post_type=events&p=153705)
        if rx.search(p.path + ("?" + p.query if pattern and p.query else "")) and u not in seen:
            seen.append(u)
    return seen


def sitemap_links(F, url, pattern, site_url, max_maps=25):
    """Links uit een sitemap (of sitemap-index, ook geneste), alleen van dezelfde site en passend bij pattern; nieuwste eerst."""
    host = urlparse(site_url).netloc.removeprefix("www.")
    rx = re.compile(pattern, re.I) if pattern else DETAIL_RE
    todo, gezien, found = [url], set(), {}
    while todo and len(gezien) < max_maps:
        sm = todo.pop(0)
        if sm in gezien:
            continue
        gezien.add(sm)
        xml = F.get_text(sm) or ""
        for blok in re.findall(r"<sitemap\b.*?</sitemap>", xml, re.S | re.I):
            loc = re.search(r"<loc>\s*(.*?)\s*</loc>", blok, re.S | re.I)
            if loc and not loc.group(1).endswith(".gz"):
                todo.append(unescape(loc.group(1)))
        for blok in re.findall(r"<url\b.*?</url>", xml, re.S | re.I):
            loc = re.search(r"<loc>\s*(.*?)\s*</loc>", blok, re.S | re.I)
            if not loc:
                continue
            u = unescape(loc.group(1)).split("#")[0]
            p = urlparse(u)
            if p.netloc.removeprefix("www.") != host or not rx.search(p.path + ("?" + p.query if p.query else "")):
                continue
            mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", blok, re.S | re.I)
            found.setdefault(u, mod.group(1) if mod else "")
    return sorted(found, key=lambda u: found[u], reverse=True)


def next_pages(soup, page_url, html):
    out = []
    ln = soup.find("link", rel="next") or soup.find("a", rel="next")
    if ln and ln.get("href"):
        out.append(urljoin(page_url, ln["href"]))
    # Genummerde vervolgpagina's van dezelfde agenda: "?page=2", "/page/2/"
    path = urlparse(page_url).path.rstrip("/")
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"]).split("#")[0]
        p = urlparse(u)
        if p.netloc == urlparse(page_url).netloc and re.search(r"[?&](page|pagina|p)=\d+$|/page/\d+/?$", u) \
                and re.sub(r"/page/\d+/?$", "", p.path).rstrip("/") == path and u not in out:
            out.append(u)
    return out


MON = r"(jan|feb|mrt|maa|mar|apr|mei|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.?"
# "12, 13 & 14 juni 2027", "5 t/m 7 juni", "24-26 juli 2026", "vr 3 - zo 5 juli"
FEST_RE = re.compile(r"\b(\d{1,2})(?:\s*(?:[-–—/&,]|t/m|tot en met|en|and)\s*(?:[a-z]{2,9}\.?\s+)?(\d{1,2}))*\s+"
                     + MON + r"(?:\s+'?(\d{4}|\d{2}))?\b", re.I)
# "30 mei - 1 juni 2027", "Fri 27 Aug till Mon 30 Aug"
FEST2_RE = re.compile(r"\b(\d{1,2})\s+" + MON + r"(?:\s+(\d{4}))?\s*(?:[-–—]|t/m|tot en met|tot|till|until)\s*(?:[a-z]{2,9}\.?\s+)?"
                      r"(\d{1,2})\s+" + MON + r"(?:\s+(\d{4}))?", re.I)
# Engels, maand eerst: "June 24 - 27", "April 15-18, 2027", "June 24-25-26", "August 14 2027"
FEST3_RE = re.compile(r"\b" + MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:[-–—&/]|t/m|to|till|until)\s*(?:" + MON
                      + r"\s+)?(\d{1,2})(?:st|nd|rd|th)?)*(?:,?\s+(\d{4}))?(?![\d:])", re.I)
# Cijfers: "26.11.2026 t/m 17.01.2027", "14.08.2027"
FESTNUM_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?:\s*(?:[-–—]|t/m|tot en met|tot)\s*"
                        r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2}))?")


def festival_event(src, F, log):
    """Eén item per festival: naam + periode, gelezen van de festivalsite (JSON-LD of tekst)."""
    html = F.get(src["agenda_url"])
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    evs = [e for e in (from_jsonld(o, src["agenda_url"]) for o in jsonld_events(soup)) if e]
    evs = sorted((e for e in evs if (e.get("end") or e["date"]) >= TODAY.isoformat()), key=lambda e: e["date"])
    # Festivalsites tonen vaak ook hun losse clubavonden (Awakenings tijdens ADE in oktober): als we weten in welke
    # maand het festival is (bronnen.json "month"), dan geen losse datums ver daarvandaan. Een periode is betrouwbaar.
    usual = MONTHS.get(str(src.get("month", "")).lower()[:3])
    if usual:
        evs = [e for e in evs if e.get("end") or min((int(e["date"][5:7]) - usual) % 12, (usual - int(e["date"][5:7])) % 12) <= 1]
    # "date_regex" in bronnen.json: datums die alleen in de broncode staan (ADE: "dayOne":"2026-10-21" ... "dayFive":"2026-10-25"
    # in een script). Groep 1 = begin, groep 2 (optioneel) = eind, als JJJJ-MM-DD.
    if not evs and src.get("date_regex"):
        m = re.search(src["date_regex"], html, re.S)
        if m and re.fullmatch(r"\d{4}-\d\d-\d\d", m.group(1)):
            a = m.group(1)
            b = m.group(2) if (m.lastindex or 0) >= 2 and re.fullmatch(r"\d{4}-\d\d-\d\d", m.group(2) or "") else a
            if b >= TODAY.isoformat() and a <= b:
                evs = [{"date": a, "end": b if b != a else None}]
    if evs:
        d0, d1 = evs[0]["date"], max(e.get("end") or e["date"] for e in evs)
    else:
        for bad in soup.find_all(["script", "style", "noscript"]):
            bad.decompose()
        head = " ".join(filter(None, [(soup.find("meta", attrs={"name": "description"}) or {}).get("content"),
                                      (soup.find("meta", property="og:description") or {}).get("content"),
                                      soup.get_text(" ", strip=True)[:8000]]))

        def mk(day, mon, yy, pos):
            m = MONTHS[mon.lower()[:3]] if not str(mon).isdigit() else int(mon)
            if not yy:
                # "Noorderzon 2026 vindt plaats van 20 - 30 augustus": jaartal kort ervoor geldt. Dan niet
                # doorschuiven naar volgend jaar (anders wordt een oude tekst een valse datum voor volgend jaar).
                hint = re.findall(r"\b(20\d{2})\b", head[max(0, pos - 40):pos])
                if hint:
                    return dt.date(int(hint[-1]), m, int(day))
            y = (2000 + int(yy) if yy and len(yy) == 2 else int(yy)) if yy else TODAY.year
            d = dt.date(y, m, int(day))
            return d.replace(year=y + 1) if not yy and d < TODAY - dt.timedelta(days=7) else d

        def ok(a, b, pos=None):
            # "tickets on sale until June 2nd" / "t/m 5 mei bestellen": geen festivaldatum
            if pos is not None and a == b and re.search(r"(until|till|tot|t/m|before|voor|deadline|uiterlijk)\s*$",
                                                        head[max(0, pos - 12):pos], re.I):
                return False
            # Een eendaagse datum van vandaag komt vrijwel altijd uit een nieuwsbericht
            if a == b == TODAY:
                return False
            # Bekend in welke maand het festival normaal is (bronnen.json "month")? Dan niet ver daarvandaan
            # (alleen bij een losse datum: een duidelijke periode op de site is betrouwbaarder dan onze lijst)
            usual = MONTHS.get(str(src.get("month", "")).lower()[:3])
            if a == b and usual and min((a.month - usual) % 12, (usual - a.month) % 12) > 1:
                return False
            return a <= b and (b - a).days < 75 and b >= TODAY and a.year <= TODAY.year + 1

        cands = []  # (positie, start, eind): de eerste geldige periode in de tekst wint
        for m in FEST2_RE.finditer(head):
            try:
                a = mk(m.group(1), m.group(2), m.group(3) or m.group(6), m.start())
                b = mk(m.group(4), m.group(5), m.group(6), m.start())
            except ValueError:
                continue
            if ok(a, b, m.start()):
                cands.append((m.start(), a, b))
                break
        for m in FEST_RE.finditer(head):
            try:
                a = mk(m.group(1), m.group(3), m.group(4), m.start())
                b = mk(m.group(2), m.group(3), m.group(4), m.start()) if m.group(2) else a
            except ValueError:
                continue
            if ok(a, b, m.start()):
                cands.append((m.start(), a, b))
                break
        for m in FEST3_RE.finditer(head):
            try:
                a = mk(m.group(2), m.group(1), m.group(5), m.start())
                b = mk(m.group(4), m.group(3) or m.group(1), m.group(5), m.start()) if m.group(4) else a
            except ValueError:
                continue
            if ok(a, b, m.start()):
                cands.append((m.start(), a, b))
                break
        for m in FESTNUM_RE.finditer(head):
            try:
                a = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                b = dt.date(int(m.group(6)), int(m.group(5)), int(m.group(4))) if m.group(4) else a
            except ValueError:
                continue
            if ok(a, b, m.start()):
                cands.append((m.start(), a, b))
                break
        found = min(cands, key=lambda c: c[0])[1:] if cands else None
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
    if src.get("platform") in film.PLATFORMS:
        return film.scrape(src, F, cfg, log)
    if src.get("platform") in museum.PLATFORMS:
        return museum.scrape(src, F, cfg, log)
    if src.get("platform") in venues.PLATFORMS:
        evs = venues.scrape(src, F, cfg, log)
        if evs is not None:  # None: platform herkende de site niet, dan de gewone uitlezer
            return evs
    # Tentoonstellingen: periode ("t/m ...") in plaats van één datum
    text_reader = museum.from_text_museum if src.get("type") == "museum" else from_text
    # Films draaien vaak meerdere keren per dag: dan hoort de tijd bij de sleutel
    k = (lambda e: (e["date"], e["time"], e["title"].lower())) if src.get("type") == "film" \
        else (lambda e: (e["date"], e["title"].lower()))
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
        # "blocks": hele agenda op één pagina in blokken zonder eigen pagina (uitklapblokken bij De Ketel, Ons Koningsoord).
        # {"selector": "div.accordion", "title": ".accordion__title"}: elk blok is één voorstelling; titel = dat element
        # of anders de eerste regel. Datum, tijd, prijs en uitverkocht/afgelast zoals bij een voorstellingspagina.
        bl = src.get("blocks")
        if bl:
            for el in soup.select(bl["selector"]):
                t_el = el.select_one(bl["title"]) if bl.get("title") else None
                regels = el.get_text("\n", strip=True).split("\n")
                titel = (t_el.get_text(" ", strip=True) if t_el else regels[0] if regels else "")
                titel = re.split(r"\s+\|\s+", titel)[0].strip(" |-–")   # "Workshop Tegeltjespracht | zaterdag 10 oktober ..."
                if len(titel) < 3:
                    continue
                if t_el:
                    t_el.decompose()
                mini = BeautifulSoup(f"<html><body><main><h1>{escape(titel)}</h1>{el}</main></body></html>", "html.parser")
                ev = from_text(mini, url.split("#")[0] + "#" + re.sub(r"[^a-z0-9]+", "-", titel.lower()).strip("-")[:60])
                if ev and ev.get("date"):
                    ev["title"] = titel
                    events.setdefault(k(ev), ev)
            continue
        # "listing_jsonld": false = de JSON-LD van het overzicht klopt niet (Paard: wintertijd een uur mis),
        # dan alleen de voorstellingspagina's zelf lezen
        for o in (jsonld_events(soup) if src.get("listing_jsonld", True) else []):
            ev = from_jsonld(o, url)
            # Nummer als naam (sommige filmsites): die voorstelling halen we van de filmpagina zelf
            if ev and not re.fullmatch(r"[\d\s#-]+", ev["title"]):
                events.setdefault(k(ev), ev)
        for u in detail_links(soup, url, src.get("link_pattern"), src.get("link_attrs", ())):
            if u not in links:
                links.append(u)
        pages += [p for p in next_pages(soup, url, html) if p not in seen_pages]

    # Links uit een JSON-lijst (WordPress REST e.d.), bv. Mezz: {"url": ".../wp-json/wp/v2/event?per_page=100&page={page}",
    # "path": "prod.link"}. Daarna gewoon de voorstellingspagina's lezen.
    lj = src.get("links_json")
    if lj:
        for page in range(1, lj.get("max_pages", 10) + 1):
            data = F.get_json(lj["url"].replace("{page}", str(page)))
            if not isinstance(data, list) or not data:
                break
            for item in data:
                v = item
                for part in lj.get("path", "link").split("."):
                    v = v.get(part) if isinstance(v, dict) else None
                # "template": van een slug een link maken (Boerderij: seo_slug -> https://.../programma/<slug>/)
                if isinstance(v, str) and v and lj.get("template") and not v.startswith("http"):
                    v = lj["template"].format(v.strip("/"))
                if isinstance(v, str) and v.startswith("http") and v not in links:
                    links.append(v)
            if "{page}" not in lj["url"]:
                break

    # "sitemap": voorstellingslinks uit de sitemap van de site zelf (als de agenda met JavaScript wordt gebouwd en de
    # API in robots.txt verboden is, Amstelveen/Lievekamp/Zwolle/Atlas). {"url": ".../sitemap.xml", "pattern": "^/voorstelling/"}
    # (zonder pattern: link_pattern). Nieuwste eerst (lastmod), zodat max_details naar de komende voorstellingen gaat.
    sm = src.get("sitemap")
    if sm:
        for u in sitemap_links(F, sm["url"], sm.get("pattern") or src.get("link_pattern"), src["agenda_url"]):
            if u not in links:
                links.append(u)

    known = {e["url"] for e in events.values()}
    fresh = (TODAY - dt.timedelta(days=cfg.get("detail_refresh_days", 7))).isoformat()
    fetched = 0
    for u in links[:src.get("max_details", cfg.get("source_max_details", 250))]:
        if u in known:
            continue
        c = cache.get(u)
        # Opnieuw ophalen als de cache oud is, of als de voorstelling binnen twee weken is (tijden/uitverkocht).
        soon = c and c.get("ev") and c["ev"]["date"] <= (TODAY + dt.timedelta(days=14)).isoformat()
        if c and c.get("v") == CACHE_V and c.get("at", "") >= fresh and not (soon and c.get("at") != TODAY.isoformat()):
            evs = c.get("evs") or ([c["ev"]] if c.get("ev") else [])
        else:
            html = F.get(u)
            fetched += 1
            evs = []
            if html:
                soup = BeautifulSoup(html, "html.parser")
                evs = [e for e in (from_jsonld(o, u) for o in jsonld_events(soup)) if e]
                for e in evs:
                    # Sommige sites zetten een nummer of kopje als naam in de JSON-LD; neem dan de paginatitel
                    if re.fullmatch(r"[\d\s#-]+", e["title"]) or GENERIC_TITLE.match(e["title"]):
                        e["title"] = pick_title(soup, u)
                if not evs:
                    e = text_reader(soup, u)
                    evs = [e] if e else []
                if src.get("timetable") and len(evs) == 1 and not evs[0].get("end"):  # settijden (013, Tivoli); niet bij meerdaags
                    evs[0].update(venues.detail_times(soup, evs[0]["title"]))
                    if any("<" in x for x in evs[0].get("support") or []):  # HTML-rommel uit de JSON-LD (Tivoli)
                        evs[0].pop("support")
                # Alleen een deel van het gebouw (bv. Willem Twee: "Locatie Poppodium", niet de Kunstruimte)
                page_txt = soup.get_text(" ", strip=True)
                if src.get("must_contain") and not re.search(src["must_contain"], page_txt, re.I):
                    evs = []
                if src.get("must_not_contain") and re.search(src["must_not_contain"], page_txt, re.I):
                    evs = []
            cache[u] = {"at": TODAY.isoformat(), "v": CACHE_V, "ev": evs[0] if len(evs) == 1 else None}
            if len(evs) > 1:
                cache[u]["evs"] = evs
        for ev in evs:
            events.setdefault(k(ev), ev)
    skip = re.compile("|".join(map(re.escape, cfg.get("skip_title_words", []))) or "(?!)", re.I)
    out = []
    for e in events.values():
        # "Meeuw — Het Nationale Theater | regie Nina Spijkers" -> "Meeuw"
        # "Wodan Boys // zaterdag 10 oktober, Willem Twee Den Bosch" -> "Wodan Boys"
        parts = [p.strip() for p in re.split(r"\s+[—|]\s+|\s*//\s*", e["title"]) if p.strip()]
        # "Jazz Podium Goirle | Laranja": is het eerste deel de naam van de bron zelf, dan het tweede deel
        if len(parts) > 1 and re.sub(r"\W", "", parts[0].lower()) in re.sub(r"\W", "", src["name"].lower()):
            parts = parts[1:]
        if parts and len(parts[0]) >= 3:
            e["title"] = parts[0]
        # "Axel Rudi Pell - Poppodium Boerderij": naam van het podium achteraan eraf
        kaal = re.sub(r"\s+[-–]\s+" + re.escape(re.sub(r"\s*\(.*?\)", "", src["name"])) + r"\s*$", "", e["title"], flags=re.I)
        if len(kaal) >= 3:
            e["title"] = kaal
        # "title_strip": regex die van de titel af moet (Vera: " 2026" achteraan); "geen_prijs": prijs op de pagina klopt niet
        if src.get("title_strip"):
            kaal = re.sub(src["title_strip"], "", e["title"], flags=re.I).strip()
            if len(kaal) >= 3:
                e["title"] = kaal
        if src.get("geen_prijs"):
            e.pop("price", None)
        # "Donderdag 8 oktober v.v. EIGEN WIJS" / "9 t/m 11 oktober Biergarten": datum vooraan eraf
        stripped = re.sub(r"^(?:(?:ma|di|wo|do|vr|za|zo)[a-z]*\.?\s+)?\d{1,2}(?:\s*(?:t/m|-|–)\s*\d{1,2})?\s+(?:jan|feb|mrt|maa|apr|mei|jun|jul|aug|sep|okt|nov|dec)[a-z]*\.?"
                          r"(?:\s+20\d\d)?\s*(?:v\.v\.|:|-|–)?\s*", "", e["title"], flags=re.I)
        stripped = re.sub(r"\s+\d{1,2}[:.]\d{2}(?:\s*(?:-|–|tot)\s*\d{1,2}[:.]\d{2})?\s*(?:uur)?\s*$", "", stripped)  # "... 13:00 - 23:00"
        if stripped != e["title"] and len(stripped) >= 3:
            e["title"] = stripped
        if src.get("type") == "film":
            # "The Incomer - Filmvoorstelling" / "Film: Pressure" -> filmtitel
            e["title"] = re.sub(r"\s+-\s+(filmvoorstelling|film|voorstelling)\b.*$|^film:\s*", "", e["title"], flags=re.I).strip()
            # Een 'tijd' vóór 9 uur is bij film vrijwel altijd de speelduur (1:35), geen aanvang
            if e.get("time") and e["time"] < "09:00":
                e["time"] = None
        if GENERIC_TITLE.match(e["title"]) or re.match(r"(programma|studio/k)\s*-", e["title"], re.I):
            continue  # kopje van de site, geen voorstelling
        out.append(e)
    # Vangnet: dezelfde titel bij 3+ pagina's waarvan de link niets met die titel te maken heeft,
    # is een sitekopje ("Agenda overzicht"), geen voorstellingsnaam. Een reeks van één voorstelling
    # (zelfde titel, link met die titel erin) blijft gewoon staan.
    count = {}
    for e in out:
        count.setdefault(e["title"], set()).add(e["url"])
    for e in out:
        urls = count[e["title"]]
        key = re.sub(r"[^a-z0-9]", "", e["title"].lower())[:8]
        if src.get("type") == "film":
            break  # films draaien vaak, met een ticketnummer als link: dat is geen sitekopje
        if len(urls) >= 3 and sum(key in re.sub(r"[^a-z0-9]", "", u.lower()) for u in urls) < len(urls) / 2:
            slug = _slug_title(e["url"])
            if slug and not re.fullmatch(r"[\d\s]+", slug):
                e["title"] = slug
    out = [e for e in out if not skip.search(e["title"])]  # geen bibliotheekdiensten, spreekuren e.d.
    log(f"  {src['name']}: {len(out)} items ({len(links)} links, {fetched} opgehaald)")
    return out


ANTWOORDEN = {}  # antwoordcodes per site van de laatste collect()


def local_key(src):
    """Sleutel in lokaal.json: naam + soort (Gigant staat er als poppodium én als filmhuis in)."""
    return f"{src['name']}|{src.get('type', '')}"


def load_local(log=print):
    """Resultaten van de bronnen die alleen vanaf de eigen computer van de eigenaar werken (scraper/lokaal.py -> lokaal.json)."""
    if not LOKAAL.exists():
        return {}
    try:
        data = json.loads(LOKAAL.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("bronnen"), dict):
            raise ValueError("onverwachte opbouw")
        age = (TODAY - dt.date.fromisoformat(str(data.get("datum", "2000-01-01"))[:10])).days
    except (OSError, ValueError, TypeError) as e:   # een kapot bestand van de eigen computer mag de nachtrun niet laten crashen
        log(f"  lokaal.json onleesbaar ({e.__class__.__name__}: {e}): niet gebruikt")
        return {}
    if age > 21:
        log(f"  lokaal.json is {age} dagen oud: niet meer gebruikt")
        return {}
    t0, out = TODAY.isoformat(), {}
    for name, evs in data["bronnen"].items():
        if not isinstance(name, str) or not isinstance(evs, list) or len(evs) > 5000:
            continue
        ok = [e for e in evs if isinstance(e, dict) and isinstance(e.get("title"), str) and isinstance(e.get("url"), str)
              and isinstance(e.get("date"), str) and re.fullmatch(r"\d{4}-\d\d-\d\d", e["date"])
              and all(e.get(k) is None or isinstance(e[k], str) for k in ("time", "end", "doors", "start"))]
        out[name] = [e for e in ok if str(e.get("end") or e["date"]) >= t0]
    return out


def collect(cfg, only=None, log=print, local=False):
    """Geeft [(bron, [events])] terug voor alle bronnen in bronnen.json.
    Bronnen met "local_only" blokkeren datacenters (GitHub): die haalt scraper/lokaal.py (local=True) op
    vanaf de eigen computer van de eigenaar; de gewone run neemt dan de items uit lokaal.json over."""
    if not BRONNEN.exists():
        return []
    allsrc = [s for s in json.loads(BRONNEN.read_text(encoding="utf-8"))
              if s.get("agenda_url") and s.get("enabled", True) and (not only or only.lower() in s["name"].lower())]
    srcs = [s for s in allsrc if bool(s.get("local_only")) == local]
    from_local = [] if local else [s for s in allsrc if s.get("local_only")]
    cache_file = LOCAL_CACHE if local else CACHE
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    F = Fetcher(cfg["user_agent"], cfg["delay_seconds"])
    lock = threading.Lock()

    def one(src):
        local = {}
        with lock:
            local.update({k: v for k, v in cache.items()})
        try:
            evs = scrape_source(src, F, local, cfg, log)
            evs = [e for e in evs if e.get("status") != "cancelled"]  # afgelast: niet tonen
        except Exception as e:  # een kapotte site mag de rest niet tegenhouden
            log(f"  {src['name']}: fout {e.__class__.__name__}: {e}")
            evs = []
        with lock:
            cache.update({k: v for k, v in local.items() if k not in cache or v is not cache.get(k)})
        return src, evs

    # Tijdslimiet: wat na max_minutes nog niet klaar is (vaak een trage bioscoopsite) laten we schieten;
    # scrape.py houdt voor die bronnen de items van de vorige keer aan. Zo gaat niet de hele nacht verloren.
    t0 = time.time()
    pool = ThreadPoolExecutor(max_workers=cfg.get("source_workers", 12))
    futs = [(src, pool.submit(one, src)) for src in srcs]
    wait([f for _, f in futs], timeout=max(60, cfg.get("max_minutes", 200) * 60 - (time.time() - t0)))
    results = []
    for src, f in futs:
        if f.done():
            results.append(f.result())
        else:
            log(f"  {src['name']}: niet op tijd klaar, vorige gegevens blijven staan")
            results.append((src, None))
    pool.shutdown(wait=False, cancel_futures=True)
    ANTWOORDEN.clear(); ANTWOORDEN.update(F.stats)   # lokaal.py zet dit in lokaal.json (403? 404?)
    with lock:
        cache = dict(cache)
    horizon = (TODAY - dt.timedelta(days=cfg.get("cache_keep_days", 30))).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("at", "") >= horizon}
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if local:
        return results
    if from_local:
        loc = load_local(log)
        for src in from_local:
            evs = loc.get(local_key(src))
            log(f"  {src['name']}: {len(evs) if evs is not None else 'geen'} items van de eigen computer (lokaal.json)")
            results.append((src, evs))  # None = nog nooit lokaal opgehaald: vorige gegevens aanhouden
    if not only:
        # Rapport per bron: aantal items en de antwoorden van de site (403 = geblokkeerd, 404 = verkeerde link, ...)
        rep = []
        for src, evs in results:
            site = urlparse(src["agenda_url"]).netloc.removeprefix("www.")
            rep.append({"name": src["name"], "type": src.get("type"), "items": len(evs or []),
                        "niet_op_tijd": evs is None and not src.get("local_only"),
                        "lokaal": bool(src.get("local_only")),
                        "site": site, "antwoorden": F.stats.get(site, {})})
        rep.sort(key=lambda r: (r["items"] > 0, r["type"] or "", r["name"]))
        REPORT.write_text(json.dumps({"datum": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                      "werkt": sum(1 for r in rep if r["items"]), "totaal": len(rep), "bronnen": rep},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    return results
