"""Laat zien hoe een voorstellingspagina is opgebouwd: JSON-LD, titelkandidaten en elke regel met een datum of tijd.

Gebruik: python scraper/inspect_page.py <url>   (draait ook via de GitHub-workflow 'Bron testen')
"""
import json, sys
from bs4 import BeautifulSoup
import sources

CFG = json.loads((sources.ROOT / "scraper/config.json").read_text(encoding="utf-8"))
url = sys.argv[1]
if " " in url.strip():
    import runpy
    runpy.run_path(str(sources.ROOT / "scraper/probe.py"), run_name="__main__")
    sys.exit(0)
F = sources.Fetcher(CFG["user_agent"], 0)
html = F.get(url)
if not html:
    sys.exit(f"Kon {url} niet ophalen")
soup = BeautifulSoup(html, "html.parser")

print("== JSON-LD events")
for o in sources.jsonld_events(soup):
    print(json.dumps({k: o.get(k) for k in ("@type", "name", "startDate", "endDate", "url")}, ensure_ascii=False))

print("\n== Titel")
h1 = soup.find("h1")
print("h1:", h1.get_text(" ", strip=True) if h1 else None)
print("og:title:", (soup.find("meta", property="og:title") or {}).get("content"))
print("gekozen:", sources.pick_title(soup, url))

print("\n== Regels met een datum of tijd (in volgorde), met de HTML-plek erbij")
for el in soup.find_all(string=True):
    t = " ".join(el.split())
    if not t or el.parent.name in ("script", "style"):
        continue
    if sources.TXT_DATE_RE.search(t) or sources.NUM_DATE_RE.search(t) or sources.TIME_RE.search(t):
        path = ">".join(f"{p.name}{('.' + '.'.join(p.get('class', [])[:2])) if p.get('class') else ''}"
                        for p in reversed(list(el.parents)[:5]) if p.name != "[document]")
        print(f"{t[:120]!r:<70} @ {path}")

print("\n== Wat de scraper er nu van maakt")
print(sources.from_text(BeautifulSoup(html, "html.parser"), url))
