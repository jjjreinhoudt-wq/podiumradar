"""Laat zien hoe een voorstellingspagina is opgebouwd: JSON-LD, titelkandidaten en elke regel met een datum of tijd.

Gebruik: python scraper/inspect_page.py <url> [<url> ...]   (draait ook via de GitHub-workflow 'Bron testen')
Meerdere adressen met een spatie ertussen. Voorvoegsels voor één adres:
  raw:<url>            de eerste 20 KB van het antwoord zoals het is (html, json, xml, javascript)
  raw60:<url>          idem, de eerste 60 KB (getal = aantal KB, max 200)
  find:<tekst>@<url>   elke plek in het ruwe antwoord waar <tekst> staat, met 300 tekens eromheen
  seltxt<N>:<css>@<url> tekst, links en attributen van de eerste N (15) elementen
  sel:<css>@<url>      de HTML van de eerste 5 elementen die bij de CSS-selector passen (zonder plaatjes, max 8000 tekens per stuk)
  platform=<p>:<bron>  bron uit bronnen.json met dit platform uitlezen (aantallen, tijd, voorbeelden)
  bron:{json}          bron uitproberen met andere instellingen (op naam + wijzigingen, of een nieuwe bron); als enige opdracht in de invoer
  jsonkeys:<regex>@<url> sleutels in JSON (of __NEXT_DATA__) die op de regex lijken
  gql:<query>          vraag aan de Paradiso-programmadienst
  links:<url>          alle links op de pagina (gegroepeerd), scripts, formulieren en data-attributen
Robots.txt en de pauze per server gelden gewoon (ophalen gaat via sources.Fetcher).
"""
import collections, json, re, sys
from bs4 import BeautifulSoup
import sources

CFG = json.loads((sources.ROOT / "scraper/config.json").read_text(encoding="utf-8"))
F = sources.Fetcher(CFG["user_agent"], CFG["delay_seconds"])


def raw(url):
    r = F._fetch(url)
    if r is None:
        print(f"Kon {url} niet ophalen ({F.stats})")
        return None
    r.encoding = r.encoding or "utf-8"
    print(f"content-type: {r.headers.get('content-type')}  lengte: {len(r.content)}")
    return r.text


def page(url):
    html = F.get(url)
    if not html:
        print(f"Kon {url} niet ophalen ({F.stats})")
        return
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


def links(url):
    html = F.get(url)
    if not html:
        print(f"Kon {url} niet ophalen ({F.stats})")
        return
    soup = BeautifulSoup(html, "html.parser")
    groups = collections.defaultdict(list)
    for a in soup.find_all("a", href=True):
        h = a["href"]
        key = re.sub(r"[0-9a-z]{4}$", "<4>", re.sub(r"\d+", "<n>", h.split("?")[0]))
        key = "/".join(key.split("/")[:4])
        groups[key].append(h)
    print("== Links (groep: aantal, voorbeelden)")
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:60]:
        print(f"{len(v):4} {k}   {v[:3]}")
    print("\n== Scripts")
    for s in soup.find_all("script"):
        if s.get("src"):
            print("src:", s["src"])
        elif (s.string or "").strip():
            print("inline:", " ".join(s.string.split())[:300])
    print("\n== Formulieren")
    for f in soup.find_all("form"):
        print(f.get("action"), f.get("method"), [i.get("name") for i in f.find_all(["input", "select"])][:20])
    print("\n== Data-attributen (uniek, max 60)")
    seen = set()
    for el in soup.find_all(True):
        for k, v in el.attrs.items():
            if k.startswith("data-") and (k, str(v)[:80]) not in seen and len(seen) < 60:
                seen.add((k, str(v)[:80]))
                print(f"<{el.name}> {k}={str(v)[:200]!r}")
    print("\n== <link>-tags")
    for l in soup.find_all("link"):
        print(l.get("rel"), l.get("type"), l.get("href"))


ALLES = " ".join(sys.argv[1:]).strip()
# bron:{json} mag spaties bevatten: dan is de hele invoer één opdracht
for arg in ([ALLES] if ALLES.startswith("bron:{") else ALLES.split()):
    print("\n" + "#" * 100 + f"\n# {arg}\n" + "#" * 100)
    m = re.match(r"raw(\d*):(.+)$", arg)
    if m:
        txt = raw(m.group(2))
        if txt is not None:
            print(txt[: min(200, int(m.group(1) or 20)) * 1024])
        continue
    m = re.match(r"find:(.+?)@(https?://.+)$", arg)
    if m:
        txt = raw(m.group(2)) or ""
        hits = [x.start() for x in re.finditer(re.escape(m.group(1)), txt)]
        print(f"{len(hits)} keer gevonden")
        for i in hits[:15]:
            print("..." + txt[max(0, i - 300): i + 300].replace("\n", " ") + "...\n")
        continue
    m = re.match(r"sel:(.+?)@(https?://.+)$", arg)
    if m:
        html = F.get(m.group(2)) or ""
        els = BeautifulSoup(html, "html.parser").select(m.group(1))
        print(f"{len(els)} elementen")
        for el in els[:5]:
            for junk in el.find_all(["picture", "svg", "img", "source", "noscript"]):
                junk.decompose()
            print(re.sub(r"\s+", " ", str(el))[:8000] + "\n---")
        continue
    m = re.match(r"seltxt(\d*):(.+?)@(https?://.+)$", arg)
    if m:
        html = F.get(m.group(3)) or ""
        els = BeautifulSoup(html, "html.parser").select(m.group(2))
        print(f"{len(els)} elementen")
        for el in els[:int(m.group(1) or 15)]:
            print(" | ".join(el.stripped_strings)[:400], [a.get("href") for a in el.find_all("a", href=True)][:4],
                  {k: v for k, v in el.attrs.items() if k != "style"})
        continue
    m = re.match(r"platform=(\w+):(.+)$", arg)
    if m:
        import time, venues
        srcs = [b for b in json.loads(sources.BRONNEN.read_text(encoding="utf-8")) if m.group(2).lower() in b["name"].lower()]
        for src in srcs[:1]:
            t0, n0 = time.time(), sum(F.stats.get(sources.urlparse(src["agenda_url"]).netloc.removeprefix("www."), {}).values())
            evs = venues.scrape(dict(src, platform=m.group(1)), F, CFG, print) or []
            n1 = sum(F.stats.get(sources.urlparse(src["agenda_url"]).netloc.removeprefix("www."), {}).values())
            print(f"{src['name']}: {len(evs)} voorstellingen, {len({e['url'] for e in evs})} producties, "
                  f"{sum(1 for e in evs if e.get('time'))} met tijd, {sum(1 for e in evs if e.get('status') == 'sold')} uitverkocht, "
                  f"{min((e['date'] for e in evs), default='-')} t/m {max((e['date'] for e in evs), default='-')}, "
                  f"{n1 - n0} verzoeken, {time.time() - t0:.0f} s")
            for e in evs[:6] + evs[len(evs) // 2:len(evs) // 2 + 3]:
                print("   ", json.dumps(e, ensure_ascii=False))
        continue
    m = re.match(r"bron:(\{.+\})$", arg, re.S)
    if m:  # bron uitproberen met andere instellingen, zonder bronnen.json te wijzigen. Geen spaties: schrijf ze als  .
        # bron:{"name":"Little Devil","link_pattern":"/agenda/.+","max_details":20}  (bestaande bron op naam + wijzigingen)
        # bron:{"name":"Nieuw","city":"Tilburg","type":"pop","agenda_url":"https://..."}  (nieuwe bron)
        import time
        over = json.loads(m.group(1))
        src = next((dict(b) for b in json.loads(sources.BRONNEN.read_text(encoding="utf-8")) if b["name"] == over.get("name")), {})
        src.update(over)
        t0 = time.time()
        evs = sources.scrape_source(src, F, {}, CFG, print) or []
        weg = [e for e in evs if e.get("status") == "cancelled"]
        evs = [e for e in evs if e.get("status") != "cancelled"]
        print(f"== {src.get('name')}: {len(evs)} items (+{len(weg)} afgelast), {sum(1 for e in evs if e.get('time'))} met tijd, "
              f"{min((e['date'] for e in evs), default='-')} t/m {max((e['date'] for e in evs), default='-')}, {time.time() - t0:.0f} s, "
              f"antwoorden {F.stats}")
        for e in sorted(evs, key=lambda e: e["date"])[:40]:
            print("   ", json.dumps(e, ensure_ascii=False)[:300])
        continue
    m = re.match(r"jsonkeys:(.+?)@(https?://.+)$", arg)
    if m:  # JSON (los antwoord of __NEXT_DATA__/application/json in de pagina): sleutels die op de regex lijken
        txt = raw(m.group(2)) or ""
        blobs = []
        try:
            blobs.append(json.loads(txt))
        except ValueError:
            for sc in BeautifulSoup(txt, "html.parser").find_all("script", type=re.compile("json", re.I)):
                try:
                    blobs.append(json.loads(sc.string or ""))
                except ValueError:
                    pass
        rx, hits = re.compile(m.group(1), re.I), []

        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items():
                    if rx.search(str(k)) and len(hits) < 80:
                        hits.append(f"{path}.{k} = {json.dumps(v, ensure_ascii=False)[:200]}")
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o[:400]):
                    walk(v, f"{path}[{i}]")
        for b in blobs:
            walk(b, "")
        print(f"{len(blobs)} JSON-blokken")
        print("\n".join(hits))
        continue
    m = re.match(r"gql:(.+)$", arg)
    if m:  # Paradiso-programmadienst (zelfde aanvraag als de site; komma's mogen als spatie)
        import venues
        ep, key = venues.paradiso_api("https://www.paradiso.nl", F)
        js = F.post_json(ep, {"query": m.group(1)}, headers={"Authorization": f"Bearer {key}"}) if ep else None
        print(json.dumps(js, ensure_ascii=False)[:20000])
        continue
    m = re.match(r"links:(.+)$", arg)
    if m:
        links(m.group(1))
        continue
    page(arg)
