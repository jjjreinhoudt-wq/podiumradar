"""Proef van de hele schrijfstap van scrape.py zonder internet: de bronnen worden vervangen door de inhoud van de huidige
site/data.json. Controleert o.a. het opschonen, het vangnet bij stille uitval van een bron en dat er niets stuk gaat.
Draaien:  python scraper/test_scrape_offline.py"""
import copy, datetime as dt, json, pathlib, shutil, sys, tempfile
import requests

HIER = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.argv = ["scrape.py"]
def geen_netwerk(*a, **k): raise requests.ConnectionError("geen netwerk in de test")
requests.Session.get = geen_netwerk
import scrape, sources

fouten = 0
def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht; fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))

echt = json.loads((HIER.parent / "site/data.json").read_text(encoding="utf-8"))
# 'Vandaag' = de dag van data.json, zodat de test niet kapot gaat als het bestand ouder wordt
scrape.TODAY = sources.TODAY = dt.date.fromisoformat(echt["updated"][:10])
scrape.HORIZON = scrape.TODAY + dt.timedelta(days=scrape.CFG["days_ahead"])
TODAY = scrape.TODAY
def bronnen(leeg=(), extra_kapot=False):
    """[(bron, events)] zoals sources.collect() ze zou geven, opgebouwd uit data.json."""
    per = {}
    for e in echt["events"]:
        per.setdefault(e["v"], []).append(e)
    out = []
    for vid, evs in per.items():
        v = echt["venues"][vid]
        src = {"name": v["name"], "city": v["city"], "prov": v["prov"], "type": v["type"] if v["type"] != "film" else "film", "agenda_url": "https://x.nl"}
        items = [] if v["name"] in leeg else [{k: x for k, x in e.items() if k not in ("id", "v", "first_seen", "genre")} | {"genre": e["genre"]} for e in evs]
        if extra_kapot and items:
            items.append({"title": None, "date": "2026-11-01", "url": "https://x.nl"})   # onbruikbaar item uit een bron
        out.append((src, items))
    return out

def run(data_in, leeg=(), status=None, extra_kapot=False):
    """Draait scrape.main() met tijdelijke bestanden; geeft (data.json, status) terug of de exitcode."""
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        scrape.OUT, scrape.STATUS, scrape.VCACHE = t / "data.json", t / "bronstatus.json", t / "venues_cache.json"
        shutil.copy(HIER / "venues_cache.json", scrape.VCACHE)
        scrape.OUT.write_text(json.dumps(data_in), encoding="utf-8")
        scrape.BRONSTATUS = copy.deepcopy(status or {}); scrape.VEROUDERD.clear()
        scrape.geocode = lambda *a, **k: None
        sources.collect = lambda cfg, only=None, **k: bronnen(leeg, extra_kapot)
        code = 0
        try:
            scrape.main()
        except SystemExit as e:
            code = e.code
        res = json.loads(scrape.OUT.read_text(encoding="utf-8"))
        st = json.loads(scrape.STATUS.read_text(encoding="utf-8")) if scrape.STATUS.exists() else None
        return code, res, st

# 1. gewone run: bijna alles komt terug, niets kapots
code, res, st = run(echt)
check("gewone run: geen fout", code, 0)
n_in = sum(1 for e in echt["events"] if (e.get("end") or e["date"]) >= TODAY.isoformat())
check("gewone run: bijna alle items terug (>= 97%)", len(res["events"]) >= 0.97 * n_in, True)
check("gewone run: bronstatus bijgehouden", len(st) > 100, True)
check("gewone run: geen 'verouderd'", "verouderd" in res, False)
check("gewone run: velden zijn schoon", all(isinstance(e["title"], str) and e["url"] == "" or e["url"].startswith("http") for e in res["events"]), True)
check("gewone run: tijdstempel heeft het juiste formaat", bool(res["updated"]) and len(res["updated"]) == 16, True)

# 2. onbruikbare items uit een bron worden weggelaten (weinig: gewoon publiceren)
code, res, st = run(echt, extra_kapot=True)
check("onbruikbare items: wel gepubliceerd (weinig)", (code, len(res["events"]) >= 0.97 * n_in), (0, True))

# 3. stille uitval: grootste bron geeft ineens niets -> oude items blijven, met melding
groot = max(echt["venues"].items(), key=lambda kv: sum(1 for e in echt["events"] if e["v"] == kv[0]))
naam = groot[1]["name"]; vid = groot[0]
vorig = sum(1 for e in echt["events"] if e["v"] == vid)
code, res, st = run(echt, leeg=(naam,))
nu = sum(1 for e in res["events"] if e["v"] == vid)
check("stille uitval: oude items van die bron blijven", (code, nu >= 0.9 * vorig), (0, True))
check("stille uitval: gemeld als verouderd", vid in res.get("verouderd", {}), True)

# 4. te lang leeg: de items vallen weg
oud = {naam + "|" + groot[1]["type"]: {"ok": (TODAY - dt.timedelta(days=8)).isoformat(), "n": vorig}}
code, res, st = run(echt, leeg=(naam,), status=oud)
check("8 dagen leeg: items weg", (code, sum(1 for e in res["events"] if e["v"] == vid)), (0, 0))

# 5. veel kapot: niet publiceren
backup = bronnen
def bronnen_kapot(leeg=(), extra_kapot=False):
    out = backup()
    for src, items in out:
        for it in items[::2]:
            it["date"] = "2026-13-45"       # de helft onbruikbaar maar wel een tekst, dus het komt door de eerste controle
    return out
bronnen = bronnen_kapot
code, res, st = run(echt)
check("de helft onbruikbaar: niet gepubliceerd (exit 2)", code, 2)
bronnen = backup

# 6. relocate(): show bij het juiste podium (Here's The Thing, 10 okt 2026)
def ev6(venue, title, loc, date="2026-10-10", vtype="pop"):
    return {"venue": venue, "city": "Tilburg", "prov": "Noord-Brabant", "vtype": vtype, "kind": vtype, "date": date, "title": title, "loc": loc, "time": "15:00", "url": "https://x.nl/" + title}
def reloc(*evs):
    r = scrape.relocate({f"s{i}": e for i, e in enumerate(evs)})
    return sorted((e["venue"], e["title"]) for e in r.values())
check("losse plaatsnaam als locatie verhuist niets (Cul de Sac -> Schouwburg was fout)",
      reloc(ev6("Cul de Sac", "Here's The Thing", "Tilburg")), [("Cul de Sac", "Here's The Thing")])
check("meerdere plekken met 013 als hoofdlocatie: blijft bij 013, kopie bij Cul de Sac weg",
      reloc(ev6("013", "Here's The Thing", "Poppodium 013 - Next + Basement + Cul de Sac"), ev6("Cul de Sac", "Here's The Thing", "Tilburg")), [("013", "Here's The Thing")])
check("... ook als Cul de Sac geen eigen kopie heeft",
      reloc(ev6("013", "Here's The Thing", "Poppodium 013 - Next + Basement + Cul de Sac")), [("013", "Here's The Thing")])
check("'Locatie | Hall of Fame' bij 013 verhuist nog steeds naar Hall of Fame",
      reloc(ev6("013", "Show X", "Hall of Fame")), [("Hall of Fame", "Show X")])
check("... en de kopie weg als Hall of Fame hem zelf al heeft",
      reloc(ev6("013", "Show X", "Hall of Fame"), ev6("Hall of Fame", "Show X", "")), [("Hall of Fame", "Show X")])
check("onbekende locatie verhuist niets", reloc(ev6("013", "Show Y", "Ergens anders in de stad")), [("013", "Show Y")])
check("naam van een ander podium in de locatietekst, zonder eigen podium, verhuist wel",
      reloc(ev6("Cul de Sac", "Show Z", "Schouwburg & Concertzaal")), [("Schouwburg & Concertzaal Tilburg", "Show Z")])

# 7. einddatum uit JSON-LD: tot middernacht is één dag, een periode zonder tijd blijft een periode
jl = lambda **kw: sources.from_jsonld({"@type": "Event", "name": "X", **kw}, "https://x.nl/a")
check("tot middernacht (T00:00 de dag erna) is één dag", "end" in jl(startDate="2026-10-10T15:00:00+02:00", endDate="2026-10-11T00:00:00+02:00"), False)
check("nachtprogramma tot 02:00 is één dag", "end" in jl(startDate="2026-10-10T22:00:00+02:00", endDate="2026-10-11T02:00:00+02:00"), False)
check("twee dagen (tot middernacht de dag daarna) blijft een periode", jl(startDate="2026-11-28T15:00:00+01:00", endDate="2026-11-30T00:00:00+01:00").get("end"), "2026-11-30")
check("tentoonstelling met alleen datums blijft een periode", jl(startDate="2026-10-10", endDate="2026-10-11").get("end"), "2026-10-11")

# 8. afgelast alleen op eventStatus; 'cancel' in de ticketgegevens is geen afgelaste show (Neushoorn, okt 2026)
st = lambda **kw: jl(startDate="2026-10-10T20:00:00+02:00", **kw).get("status")
check("cancellationPolicy in offers: niet afgelast",
      st(offers={"@type": "Offer", "price": "20", "url": "https://x.nl/tickets?cancel_url=/terug", "cancellationPolicy": "geen restitutie"}), None)
check("eventStatus EventCancelled: afgelast", st(eventStatus="https://schema.org/EventCancelled"), "cancelled")
check("eventStatus EventPostponed: afgelast", st(eventStatus="EventPostponed"), "cancelled")
check("uitverkocht in offers blijft uitverkocht", st(offers={"availability": "https://schema.org/SoldOut"}), "sold")

# 9. verborgen tekst telt niet (Neushoorn/Webflow: 'Geannuleerd' staat verborgen op elke pagina)
from bs4 import BeautifulSoup
def ft(extra):
    html = ('<html><body><main><h1>058 Jazzcafe: Ladybirds trio</h1><div>22 okt 2026</div>' + extra +
            '<div>Deuren open:</div><div>17:00</div><div>Aanvang:</div><div>20:30</div></main></body></html>')
    return sources.from_text(BeautifulSoup(html, "html.parser"), "https://x.nl/events/ladybirds").get("status")
check("verborgen 'Geannuleerd' (w-condition-invisible): niet afgelast", ft('<div class="event-details_content w-condition-invisible">Geannuleerd</div>'), None)
check("verborgen met hidden of display:none: niet afgelast", ft('<p hidden>Afgelast</p><span style="display: none">Geannuleerd</span>'), None)
check("zichtbaar 'Geannuleerd': wel afgelast", ft('<div class="event-details_content">Geannuleerd</div>'), "cancelled")

# 10. festival: datums alleen in de broncode (ADE: window.__CONFIG__ ... "dayOne" ... "dayFive")
class _F:
    def __init__(self, html): self.html = html
    def get(self, url): return self.html
ade = {"name": "ADE", "type": "festival", "month": "oktober", "agenda_url": "https://x.nl/",
       "date_regex": "\"dayOne\":\"(\\d{4}-\\d{2}-\\d{2})\".*?\"dayFive\":\"(\\d{4}-\\d{2}-\\d{2})\""}
jaar = sources.TODAY.year + 1
html = f'<html><body><p>Nieuws: Thursday, 01 October 2020</p><script>window.__CONFIG__ = {{"edition":{{"dayOne":"{jaar}-10-21","dayTwo":"x","dayFive":"{jaar}-10-25"}}}}</script></body></html>'
evs = sources.festival_event(ade, _F(html), lambda *a: None)
check("date_regex: periode uit de broncode", [(e["date"], e.get("end")) for e in evs], [(f"{jaar}-10-21", f"{jaar}-10-25")])
oud = html.replace(str(jaar), "2020")
check("date_regex: voorbije editie geeft niets", sources.festival_event(ade, _F(oud), lambda *a: None), [])

# 11. Engelse datum met de maand vooraan (Fontys: "Thursday - October 15th")
j = sources.TODAY.year + 1
check("Engels 'October 15th, <jaar>'", sources._txt_date(f"Thursday - October 15th, {j} Address | Tilburg"), sources.dt.date(j, 10, 15))
check("'may' als werkwoord is geen datum", sources._txt_date("you may 2 tickets kopen"), None)
check("Nederlandse datum blijft voorgaan", sources._txt_date(f"15 oktober {j}, daarna October 20th"), sources.dt.date(j, 10, 15))

# 12. blokken: hele agenda op één pagina (Ons Koningsoord, De Ketel)
class _FB:
    def __init__(self, html): self.html = html
    def get(self, url): return self.html
    def get_json(self, url, params=None): return None
blokhtml = f"""<html><body><main>
<div class="accordion"><div class="accordion__item accordion__title">LA PRIMAVERA TRIO - EEN LACH EN EEN TRAAN</div>
<div class="accordion__item">ZONDAG 11 OKTOBER {j} | om 14:00 uur | Entree €15</div><div class="accordion__item">info</div></div>
<div class="accordion"><div class="accordion__item accordion__title">BOHEME BERLIJN</div>
<div class="accordion__item">VRIJDAG 13 NOVEMBER {j} | 20:15 uur | VOLGEBOEKT</div></div>
</main></body></html>"""
src = {"name": "Ons Koningsoord", "type": "thea", "agenda_url": "https://x.nl/", "blocks": {"selector": "div.accordion", "title": ".accordion__title"}}
evs = sorted(sources.scrape_source(src, _FB(blokhtml), {}, {}, lambda *a: None), key=lambda e: e["date"])
check("blokken: twee voorstellingen met titel, datum en tijd",
      [(e["title"], e["date"], e["time"]) for e in evs], [("LA PRIMAVERA TRIO - EEN LACH EN EEN TRAAN", f"{j}-10-11", "14:00"), ("BOHEME BERLIJN", f"{j}-11-13", "20:15")])
check("blokken: VOLGEBOEKT is uitverkocht", evs[1].get("status"), "sold")
check("blokken: prijs en eigen link per blok", (evs[0].get("price"), evs[0]["url"]), (15, "https://x.nl/#la-primavera-trio-een-lach-en-een-traan"))
ketel = f'<html><body><div class="hl-faq-child">Workshop Tegeltjespracht | zaterdag 1o oktober {j} - 10:30u | Zaterdag 10 oktober {j}</div></body></html>'
evs = sources.scrape_source(dict(src, blocks={"selector": "div.hl-faq-child"}), _FB(ketel), {}, {}, lambda *a: None)
check("blokken zonder titel-element: eerste deel van de eerste regel", [(e["title"], e["date"]) for e in evs], [("Workshop Tegeltjespracht", f"{j}-10-10")])

# 13. links_json met template (Boerderij), link met vraag (Vera), podiumnaam achter de titel eraf
class _FJ:
    def get(self, url):
        if "programma/axel" in url:
            return f"<html><body><main><h1>Axel Rudi Pell - Poppodium Boerderij</h1><p>za 10 okt {j} aanvang 20:30</p></main></body></html>"
        return '<html><body><a href="/?post_type=events&p=12&lang=nl">x</a><a href="/over">o</a></body></html>'
    def get_json(self, url, params=None): return [{"seo_slug": "axel-rudi-pell"}]
src = {"name": "Poppodium Boerderij", "type": "pop", "agenda_url": "https://b.nl/programma/", "link_pattern": "^/programma/[^/]+/$",
       "links_json": {"url": "https://b.nl/events.php", "path": "seo_slug", "template": "https://b.nl/programma/{}/"}}
evs = sources.scrape_source(src, _FJ(), {}, {}, lambda *a: None)
check("links_json template + podiumnaam eraf", [(e["title"], e["url"]) for e in evs], [("Axel Rudi Pell", "https://b.nl/programma/axel-rudi-pell/")])
check("link_pattern ziet ook de vraag (Vera)", sources.detail_links(sources.BeautifulSoup(_FJ().get(""), "html.parser"), "https://v.nl/programma/", r"[?&]post_type=events&p=\d+"),
      ["https://v.nl/?post_type=events&p=12&lang=nl"])

check("title_strip en geen_prijs", [(e["title"], "price" in e) for e in sources.scrape_source(dict(src, title_strip=r"\s+Pell$", geen_prijs=True), _FJ(), {}, {}, lambda *a: None)], [("Axel Rudi", False)])

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)")); sys.exit(1 if fouten else 0)
