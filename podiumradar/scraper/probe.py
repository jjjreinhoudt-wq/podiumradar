"""Tijdelijke verkenner: meerdere sites (spatie-gescheiden) bekijken. Volgt robots.txt via sources.Fetcher."""
import json, re, sys
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import sources

CFG = json.loads((sources.ROOT / "scraper/config.json").read_text(encoding="utf-8"))
F = sources.Fetcher(CFG["user_agent"], 1)
KEY = re.compile(r"agenda|programma|program|event|evenement|concert|voorstelling|activiteit|kalender|optreden|live|muziek|tickets|zien-doen", re.I)


def look(url):
    try:
        if not F.allowed(url):
            print(f"  ROBOTS VERBIEDT {url}")
            return []
        r = F._fetch(url)
    except Exception as e:
        print(f"  FOUT {url}: {e}")
        return []
    st = F.stats.get(urlparse(url).netloc.removeprefix("www."), {})
    if r is None:
        print(f"  GEEN 200 {url} codes={st}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    ev = sources.jsonld_events(soup)
    dates, samples = 0, []
    for el in soup.find_all(string=True):
        t = " ".join(el.split())
        if t and el.parent.name not in ("script", "style") and (sources.TXT_DATE_RE.search(t) or sources.NUM_DATE_RE.search(t)):
            dates += 1
            if len(samples) < 6:
                samples.append(t[:90])
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")[:80]
    print(f"  OK {url} -> {r.url} | {title!r} | jsonld={len(ev)} datumregels={dates}")
    for o in ev[:4]:
        print("    LD:", o.get("name"), o.get("startDate"), o.get("url"))
    for s in samples:
        print("    D:", s)
    host = urlparse(r.url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        u = urljoin(r.url, a["href"]).split("#")[0]
        if urlparse(u).netloc == host and u not in links and (KEY.search(urlparse(u).path) or KEY.search(a.get_text(" ", strip=True))):
            links.append(u)
    print(f"    links ({len(links)}):", " ".join(urlparse(u).path + (("?" + urlparse(u).query) if urlparse(u).query else "") for u in links[:40]))
    return links


for url in sys.argv[1].split():
    print("\n=====", url, flush=True)
    links = look(url)
    nav = [u for u in links if re.search(r"/(agenda|programma|evenementen|events?|kalender|concerten|activiteiten|optredens)/?$", urlparse(u).path, re.I)]
    for u in nav[:2]:
        if u.rstrip("/") != url.rstrip("/"):
            look(u)
