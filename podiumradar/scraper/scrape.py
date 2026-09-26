"""Podiumradar: haalt de concert- en theateragenda van Nederland op en schrijft site/data.json.

Gebruik:
  python scraper/scrape.py                                           # volledige run
  python scraper/scrape.py --only noord-brabant --max-pages 2 --dry-run --dump /tmp/pr   # snelle test
"""
import argparse, datetime as dt, json, pathlib, re, sys, time
from urllib import robotparser
import requests
from bs4 import BeautifulSoup

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
ARGS = ap.parse_args()

S = requests.Session()
S.headers["User-Agent"] = CFG["user_agent"]
RP = robotparser.RobotFileParser(CFG["base"] + "/robots.txt")
try:
    RP.read()
except Exception:
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


MONTHS = {m: i + 1 for i, m in enumerate("jan feb mrt apr mei jun jul aug sep okt nov dec".split())}
DATE_RE = re.compile(r"\b(ma|di|wo|do|vr|za|zo)\s+(\d{1,2})\s+(jan|feb|mrt|apr|mei|jun|jul|aug|sep|okt|nov|dec)\b(?:\s*'(\d{2}))?", re.I)
TIME_RE = re.compile(r"\b([01]\d|2[0-3])[:.]([0-5]\d)\b")
LINK_RE = re.compile(r"/(concert|cabaret/voorstelling|festival)/(\d+)/")
TITLE_RE = re.compile(r"^(Concert|Event|Cabaret|Festival)\s+(.*)\s+in\s+(.+)$", re.S)
TODAY = dt.date.today()
HORIZON = TODAY + dt.timedelta(days=CFG["days_ahead"])


def mkdate(day, mon, yy):
    m = MONTHS[mon.lower()]
    if yy:
        y = 2000 + int(yy)
    else:
        y = TODAY.year + (1 if m < TODAY.month - 1 else 0)
    try:
        return dt.date(y, m, int(day))
    except ValueError:
        return None


def parse_listing(html):
    """Loopt in documentvolgorde door de pagina: een datumkop geldt voor alle rijen erna."""
    soup = BeautifulSoup(html, "html.parser")
    events, cur = {}, None
    for node in soup.descendants:
        if isinstance(node, str):
            m = DATE_RE.search(node)
            if m and len(node.strip()) < 40:
                d = mkdate(m.group(2), m.group(3), m.group(4))
                if d:
                    cur = d
            continue
        if node.name != "a" or not node.get("href"):
            continue
        lm = LINK_RE.search(node["href"])
        tm = TITLE_RE.match((node.get("title") or "").strip())
        if not lm or not tm or cur is None:
            continue
        kind = {"concert": "p", "cabaret/voorstelling": "c", "festival": "f"}[lm.group(1)]
        eid = kind + lm.group(2)
        if eid in events:
            continue
        row = node.find_parent("tr") or node.find_parent("li") or node.parent
        ids = {LINK_RE.search(a["href"]).group(2) for a in row.find_all("a", href=True) if LINK_RE.search(a["href"])}
        t = None
        if len(ids) <= 1:
            mt = TIME_RE.search(row.get_text(" "))
            if mt:
                t = f"{mt.group(1)}:{mt.group(2)}"
        venue = tm.group(3).strip()
        city = None
        if row.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            for i, c in enumerate(cells):
                if c == venue and i + 1 < len(cells):
                    city = cells[i + 1]
                    break
        title = re.sub(r"(Event|Cabaret|Festival)$", "", tm.group(2)).strip()
        href = node["href"] if node["href"].startswith("http") else CFG["base"] + node["href"]
        events[eid] = {"id": eid, "date": cur.isoformat(), "time": t, "title": title,
                       "venue": venue, "city": city, "kind": tm.group(1), "url": href}
    return events, cur


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


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"events": []}
    first_seen = {e["id"]: e.get("first_seen", TODAY.isoformat()) for e in prev.get("events", [])}
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
            low = e["venue"].lower()
            vtype = CFG["venue_type_overrides"].get(e["venue"]) or \
                ("thea" if any(k in low for k in CFG["theater_keywords"]) else "pop")
            venues[vid] = {"name": e["venue"], "city": city, "prov": e["prov"], "type": vtype,
                           "lat": ll[0] if ll else None, "lon": ll[1] if ll else None}
        e["v"] = vid
        e["first_seen"] = first_seen.get(e["id"], TODAY.isoformat())
        for k in ("venue", "city", "prov", "kind"):
            e.pop(k, None)

    out = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "venues": venues,
           "events": sorted(events.values(), key=lambda e: (e["date"], e["time"] or "99"))}
    n_prev, n_new = len(prev.get("events", [])), len(out["events"])
    print(f"Klaar: {n_new} shows op {len(venues)} podia (vorige keer {n_prev})")
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
