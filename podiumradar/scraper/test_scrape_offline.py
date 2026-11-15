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

# 5b. merge_zelfde_avond(): dezelfde show twee keer bij één podium, uit twee bronnen (Carsick bij Hall of Fame, via 013 én de eigen site)
def za(*evs):
    r = scrape.merge_zelfde_avond({f"s{i}": dict({"v": "hof", "date": "2026-11-16", "genre": "Overig"}, **e) for i, e in enumerate(evs)})
    return sorted((e["title"], e.get("time"), e.get("doors"), e.get("support"), e.get("first_seen")) for e in r.values())
check("zelfde podium/dag/eerste act uit twee sites: één item, het rijkste blijft en krijgt het oudste first_seen",
      za({"title": "CARSICK + CARNE", "time": "19:30", "url": "https://hall-fame.nl/programma/carsick", "first_seen": "2026-09-30"},
         {"title": "Carsick", "time": "20:00", "doors": "19:30", "start": "21:30", "support": ["Carne"], "url": "https://www.013.nl/programma/1/carsick", "first_seen": "2026-11-12"}),
      [("Carsick", "20:00", "19:30", ["Carne"], "2026-09-30")])
check("... ook met '(013 op locatie)' achter de naam en als één tijd ontbreekt",
      len(za({"title": "TAXITAXI (013 op locatie)", "time": None, "url": "https://culdesactilburg.nl/a"}, {"title": "TAXITAXI", "time": "20:30", "url": "https://www.013.nl/b"})), 1)
check("voorprogramma dat alleen in de andere titel staat gaat mee",
      za({"title": "Coilguns + Haatdrager (NL)", "time": None, "url": "https://littledevil.nl/a"}, {"title": "Coilguns", "time": "20:45", "doors": "20:00", "url": "https://www.013.nl/b"}),
      [("Coilguns", "20:45", "20:00", ["Haatdrager"], None)])
check("matinee en avond van dezelfde site: blijven twee items",
      len(za({"title": "Hadestown", "time": "15:00", "url": "https://carre.nl/a"}, {"title": "Hadestown", "time": "20:00", "url": "https://carre.nl/b"})), 2)
check("twee sites maar meer dan twee uur uit elkaar: blijven twee items",
      len(za({"title": "Hadestown", "time": "14:00", "url": "https://a.nl/a"}, {"title": "Hadestown", "time": "20:00", "url": "https://b.nl/b"})), 2)
check("andere eerste act of algemene titel: niet samengevoegd",
      len(za({"title": "Carsick", "time": "20:00", "url": "https://a.nl/a"}, {"title": "Carne + Carsick", "time": "20:00", "url": "https://b.nl/b"},
             {"title": "Pubquiz", "time": "20:00", "url": "https://a.nl/q"}, {"title": "Pubquiz", "time": "20:00", "url": "https://b.nl/q"})), 4)

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

check("<base href> telt bij relatieve links", sources.detail_links(sources.BeautifulSoup('<base href="https://b.nl"><a href="contact/">c</a><a href="programma/x/">x</a>', "html.parser"), "https://b.nl/programma/", r"^/programma/[^/]+/?$"), ["https://b.nl/programma/x/"])
import film
props = {"data": [0, {"categories": [1, []]}], "productions": [1, [[0, {"title": [0, "Mémoire de fille"], "durationInMinutes": [0, 117],
         "screenings": [1, [[0, {"id": [0, "a"], "startAtUtc": [3, f"{j}-10-14T09:00:00.000Z"], "url": [0, "https://kassa.x.nl/#/checkout/a"]}]]]}]]]}
html = "<astro-island props='" + json.dumps(props).replace("'", "&#39;") + "'></astro-island>"
check("tricket: productions naast data, UTC naar NL-tijd", [(e["date"], e["time"], e["title"]) for e in film.tricket({"agenda_url": "https://x.nl/films/"}, _FB(html), {}, print)],
      [(f"{j}-10-14", "11:00", "Mémoire de fille")])

# 14. sitemap: index -> sitemaps -> voorstellingslinks (nieuwste eerst), alleen eigen site en passend patroon
class _FS:
    pages = {"https://t.nl/sitemap.xml": '<sitemapindex><sitemap><loc>https://t.nl/sm-shows.xml</loc></sitemap><sitemap><loc>https://t.nl/sm-pages.xml</loc></sitemap></sitemapindex>',
             "https://t.nl/sm-shows.xml": '<urlset><url><loc>https://t.nl/voorstelling/oud</loc><lastmod>2025-01-01</lastmod></url>'
                                          '<url><loc>https://www.t.nl/voorstelling/nieuw</loc><lastmod>2026-09-01</lastmod></url>'
                                          '<url><loc>https://ander.nl/voorstelling/x</loc></url></urlset>',
             "https://t.nl/sm-pages.xml": '<urlset><url><loc>https://t.nl/contact</loc></url></urlset>'}
    def get_text(self, url): return self.pages.get(url)
check("sitemap_links: index, eigen site, patroon, nieuwste eerst",
      sources.sitemap_links(_FS(), "https://t.nl/sitemap.xml", "^/voorstelling/", "https://www.t.nl/agenda"),
      ["https://www.t.nl/voorstelling/nieuw", "https://t.nl/voorstelling/oud"])

# 15. wp_shows (Leiden, Kunstmin): alle speeldata uit acf.events, status, laagste prijs, geen verleden
import venues
class _FW:
    def __init__(self, pages): self.pages = pages
    def get_json(self, url, params=None): return self.pages.get(params["page"])
wp = [{"link": "https://l.nl/v/blauw/", "title": {"rendered": "Buddy Vedder &#038; Shelley Bos &#8211; Blauw"},
       "acf": {"prices": [{"price": "42.5"}, {"price": "37.5"}, {"price": "0"}],
               "events": [{"start_date": f"{j}0925", "start_time": "20:15:00", "status": ""}, {"start_date": f"{j}0926", "start_time": "14:30:00", "status": "Uitverkocht"},
                          {"start_date": "20200101", "start_time": "20:00:00", "status": ""}]}},
      {"link": "https://l.nl/v/leeg/", "title": {"rendered": "Leeg"}, "acf": []}]
evs = venues.wp_shows({"agenda_url": "https://l.nl/agenda/"}, _FW({1: wp}), {}, print)
check("wp_shows: twee speeldata, uitverkocht, prijs 37.5, titel zonder entities",
      [(e["date"], e["time"], e.get("status"), e.get("price"), e["title"]) for e in evs],
      [(f"{j}-09-25", "20:15", None, 37.5, "Buddy Vedder & Shelley Bos – Blauw"), (f"{j}-09-26", "14:30", "sold", 37.5, "Buddy Vedder & Shelley Bos – Blauw")])
check("wp_shows: geen lijst -> None (terug naar de gewone uitlezer)", venues.wp_shows({"agenda_url": "https://l.nl/"}, _FW({}), {}, print), None)

# 16. Vue-blok 'shows' (Zwolse Theaters) en detail_date_selector (Atlas)
model = {"items": [{"information": {"date": f"za 10 okt '{str(j)[2:]}", "time": "20.00 uur", "price": "Van € 14,- tot € 27,50"}, "link": {"name": "Wachtlijst"}}]}
zw = "<html><body><main><h1>Merijn Scholten</h1><component is=\"shows\" :model='" + json.dumps(model).replace("'", "&#39;") + f"'></component><p>Ook 3 nov {j} 21:15 iets anders</p></main></body></html>"
geweest = "<html><body><main><h1>Oud</h1><component is=\"shows\" :model='{\"items\": []}'></component><p>Ook 3 nov " + str(j) + " 21:15 iets anders</p></main></body></html>"
class _FD:
    def __init__(self, pages): self.pages = pages
    def get(self, url): return self.pages.get(url)
    def get_json(self, url, params=None): return None
src = {"name": "Zwolse Theaters", "type": "thea", "agenda_url": "https://z.nl/agenda", "link_pattern": "^/programma/"}
pages = {"https://z.nl/agenda": '<a href="/programma/a">a</a><a href="/programma/b">b</a>', "https://z.nl/programma/a": zw, "https://z.nl/programma/b": geweest}
evs = sources.scrape_source(src, _FD(pages), {}, {}, lambda *a: None)
check("vue_shows: datum, tijd, prijs, wachtlijst = uitverkocht; al geweest = niets",
      [(e["title"], e["date"], e["time"], e.get("price"), e.get("status")) for e in evs], [("Merijn Scholten", f"{j}-10-10", "20:00", 14, "sold")])
atlas = (f"<html><body><header><h1>The Bodyguard</h1><span class='perf-date perf-page'> WO 07 APR {j} <div> 20:00 uur Grote Zaal <span>vanaf € 67,00</span></div></span></header>"
         f"<p>Speelt t/m 11 april {j}. Vrienden € 10,00 korting. Ook 1 feb {j} 15:00 andere show</p></body></html>")
src = {"name": "Atlas Theater", "type": "thea", "agenda_url": "https://a.nl/sitemap-pagina/", "link_pattern": "^/voorstellingen/", "detail_date_selector": "span.perf-date.perf-page"}
pages = {"https://a.nl/sitemap-pagina/": '<a href="/voorstellingen/bg-07-apr/">x</a><a href="/voorstellingen/info/">y</a>', "https://a.nl/voorstellingen/bg-07-apr/": atlas,
         "https://a.nl/voorstellingen/info/": f"<html><body><main><h1>Info</h1><p>3 mei {j} 20:00</p></main></body></html>"}
evs = sources.scrape_source(src, _FD(pages), {}, {}, lambda *a: None)
check("detail_date_selector: alleen het blok telt (geen eind, geen korting), pagina zonder blok = niets",
      [(e["date"], e["time"], e.get("price"), e.get("end")) for e in evs], [(f"{j}-04-07", "20:00", 67, None)])

# 17. festivals: dagreeksen met + • . | en "en"; geen verzonnen data uit tekst zonder jaartal; nacht na middernacht
def fest(txt, month):
    evs = sources.festival_event({"name": "X", "type": "festival", "month": month, "agenda_url": "https://x.nl/"},
                                 _F(f"<html><head><title>{txt}</title></head><body><p>{txt}</p></body></html>"), lambda *a: None)
    return [(e["date"], e.get("end")) for e in evs]
for naam, txt, mnd, verwacht in [
        ("Pinkpop •", f"Pinkpop – 18 • 19 • 20 juni {j}", "juni", [(f"{j}-06-18", f"{j}-06-20")]),
        ("Lowlands +", f"Tot volgend jaar op 20 + 21 + 22 augustus {j}.", "augustus", [(f"{j}-08-20", f"{j}-08-22")]),
        ("North Sea Jazz • zonder spaties", f"09•10•11 JULI {j} Ahoy", "juli", [(f"{j}-07-09", f"{j}-07-11")]),
        ("Wildeburg punten", f"8.9.10.11 juli {j}", "juli", [(f"{j}-07-08", f"{j}-07-11")]),
        ("NFF 'en' tussen twee datums", f"tussen 24 sept en 1 okt {j}", "september", [(f"{j}-09-24", f"{j}-10-01")]),
        ("oude editie zonder jaartal: niets", "Psy-Fi 9-13 July Stölln", "juli", []),
        ("Bevrijdingsfestival '5 mei' zonder jaartal: niets", "Bevrijdingsfestival 5 mei Den Bosch", "mei", []),
        ("zonder jaartal maar pagina noemt volgend jaar", f"9-13 July, see you in {j}", "juli", [(f"{j}-07-09", f"{j}-07-13")]),
        ("losse + in een prijs maakt geen periode", f"5 + 2 euro ... 3 juni {j}", "juni", [(f"{j}-06-03", None)])]:
    check(f"festival: {naam}", fest(txt, mnd), verwacht)
check("meerdaags met laatste nacht tot 01:00: eindigt de dag ervoor (Lente Kabinet)",
      jl(startDate=f"{j}-05-15T12:00:00+02:00", endDate=f"{j}-05-16T23:00:00.000Z").get("end"), f"{j}-05-16")

# 18. JSON-LD-naam is de uitvoerder, de kop is de voorstelling (Schouwburg Tilburg, Dikkie Dik)
u = "https://www.schouwburgconcertzaaltilburg.nl/nl/agenda/op-avontuur-met-dikkie-dik-trapperdetrap"
kop = sources.BeautifulSoup("<html><head><meta property='og:title' content='Op avontuur met Dikkie Dik (2+) - Trapperdetrap'></head><body><h1>Op avontuur met Dikkie Dik (2+)</h1></body></html>", "html.parser")
check("kop wint als die bij de link past en de JSON-LD-naam niet", sources.beter_dan_jsonld("Trapperdetrap &amp; Het Concertgebouw", kop, u), "Op avontuur met Dikkie Dik (2+)")
check("gewone JSON-LD-naam blijft staan", sources.beter_dan_jsonld("Op avontuur met Dikkie Dik", kop, u), "Op avontuur met Dikkie Dik")
check("korte link zonder titelwoorden: JSON-LD blijft", sources.beter_dan_jsonld("Trapperdetrap", kop, "https://x.nl/agenda/12345"), "Trapperdetrap")

# 19. één evenement op meer podia tegelijk (Herrie op de Heuvel bij Cul de Sac én Café Weemoed): één kaartje met 'ook'
VN = {"cds": {"name": "Cul de Sac", "city": "Tilburg", "type": "cafe"}, "wee": {"name": "Café Weemoed", "city": "Tilburg", "type": "cafe"},
      "lit": {"name": "Little Devil", "city": "Tilburg", "type": "cafe"}, "sch": {"name": "Schouwburg", "city": "Tilburg", "type": "thea"},
      "bre": {"name": "Mezz", "city": "Breda", "type": "pop"}}
def mv(items):
    evs = {f"e{i}": dict(e, id=f"e{i}", date=e.get("date", f"{j}-11-04"), time=e.get("time", "20:30"), url=e.get("url", f"https://{e['v']}.nl/{i}"),
                         genre=e.get("genre", "Overig"), first_seen=e.get("first_seen", f"{j}-10-23")) for i, e in enumerate(items)}
    out = scrape.merge_multi_venue(evs, VN)
    return sorted((e["v"], e["title"], [o["v"] for o in e.get("ook", [])], e["first_seen"]) for e in out.values())
check("deelverzameling van woorden, zelfde stad/dag/tijd: samengevoegd, kortste titel voorop, oudste first_seen",
      mv([{"v": "wee", "title": "Herrie op de korte heuvel", "first_seen": f"{j}-10-21"}, {"v": "cds", "title": "Herrie op de Heuvel"}, {"v": "lit", "title": "Herrie op de Heuvel!"}]),
      [("cds", "Herrie op de Heuvel", ["wee", "lit"], f"{j}-10-21")])
check("andere tijd: apart", mv([{"v": "wee", "title": "Herrie op de Heuvel", "time": "21:00"}, {"v": "cds", "title": "Herrie op de Heuvel"}]),
      [("cds", "Herrie op de Heuvel", [], f"{j}-10-23"), ("wee", "Herrie op de Heuvel", [], f"{j}-10-23")])
check("andere stad: apart", mv([{"v": "bre", "title": "Herrie op de Heuvel"}, {"v": "cds", "title": "Herrie op de Heuvel"}]),
      [("bre", "Herrie op de Heuvel", [], f"{j}-10-23"), ("cds", "Herrie op de Heuvel", [], f"{j}-10-23")])
check("algemene titel (pubquiz, open podium): nooit samengevoegd",
      mv([{"v": "wee", "title": "De grote pubquiz avond"}, {"v": "cds", "title": "De grote pubquiz avond"}, {"v": "wee", "title": "Open podium avond"}, {"v": "lit", "title": "Open podium avond"}]),
      [("cds", "De grote pubquiz avond", [], f"{j}-10-23"), ("lit", "Open podium avond", [], f"{j}-10-23"), ("wee", "De grote pubquiz avond", [], f"{j}-10-23"), ("wee", "Open podium avond", [], f"{j}-10-23")])
check("theater en film doen niet mee", mv([{"v": "sch", "title": "Herrie op de Heuvel"}, {"v": "cds", "title": "Herrie op de Heuvel"}, {"v": "wee", "title": "Herrie op de Heuvel", "genre": "Film"}]),
      [("cds", "Herrie op de Heuvel", [], f"{j}-10-23"), ("sch", "Herrie op de Heuvel", [], f"{j}-10-23"), ("wee", "Herrie op de Heuvel", [], f"{j}-10-23")])
check("korte of eenwoordige titel (band 'Jungle' in twee cafés): apart", mv([{"v": "wee", "title": "Jungle live"}, {"v": "cds", "title": "Jungle live"}]),
      [("cds", "Jungle live", [], f"{j}-10-23"), ("wee", "Jungle live", [], f"{j}-10-23")])
s_out, _ = scrape.schoon.schoon_alles({"updated": "x", "venues": {k: dict(v, prov="NB") for k, v in VN.items()},
                                        "events": [{"id": "e1", "v": "cds", "title": "Herrie", "date": f"{j}-11-04", "time": "20:30", "url": "https://c.nl",
                                                    "ook": [{"v": "wee", "url": "https://w.nl/x"}, {"v": "onbekend", "url": "https://q.nl"}, {"v": "cds", "url": "https://c.nl"}]}]})
check("opschonen: 'ook' houdt alleen bekende andere podia, en dat podium blijft in venues", (s_out["events"][0]["ook"], sorted(s_out["venues"])), ([{"v": "wee", "url": "https://w.nl/x"}], ["cds", "wee"]))

# AFAS Live: naam, datum en uitverkocht uit de agenda (één regel per speeldatum); tijden en prijs uit het datumblok en het
# tijdschema onderaan de voorstellingspagina. Niet uit de paginatekst: daar staat de start van de voorverkoop ('om 10:00 uur').
def _afas_rij(slug, titel, datum, tijd="", klasse="st-none", extra=""):
    return (f'<article class="agendaV2-item {klasse}" id="_agenda_1"><div class="row inner"><a aria-hidden="true" class="rowImg" href="https://www.afaslive.nl/agenda/{slug}"><figure></figure></a>'
            f'<div class="mid"><a class="rowMain" href="https://www.afaslive.nl/agenda/{slug}"><h4>{titel}{f" <time>{tijd}</time>" if tijd else ""}</h4>'
            f'<p class="date">{extra}<span class="d">{datum}</span></p></a><div class="btns"><a class="btnV2 tickets" href="https://t.nl/x"><span class="lbl">tickets</span></a>'
            f'{"<span>Uitverkocht!</span>" if "soldout" in klasse else ""}</div></div></div></article>')
def _afas_blok(naam, datum, tijd="", prijzen_="<li>Entree vanaf<span>€ 78,54</span></li>"):
    return (f'<details><summary><div class="desktop"><date>{datum}</date></div></summary><div class="gridFrame"><div class="grid-item left"><h3>{naam}</h3>'
            f'<datetime>{datum}{f" - <time>{tijd}</time>" if tijd else ""}</datetime><ul>{prijzen_}</ul></div><div class="grid-item">De kaartverkoop start vrijdag om 10:00 uur.</div></div></details>')
def _afas_pagina(blokken, tabs, acts=""):
    knoppen = "".join(f'<button data-tab="_tab{i}">{k}</button>' for i, (k, _) in enumerate(tabs))
    inhoud = "".join(f'<div class="floated tabsContent" id="_tab{i}">{c}</div>' for i, (_, c) in enumerate(tabs))
    return (f'<html><head><title>X op 1 en 4 december {j} in AFAS Live - AFAS Live</title></head><body><h1>Agenda</h1><div class="row agenda-item"><ul class="act">{acts}</ul>'
            f'<div class="floated intro"><p>De voorverkoop start vrijdag 29 mei om 10:00 uur.</p></div><div class="floated dates">{"".join(blokken)}</div>'
            f'<div class="tabsContainer timesTable" id="timetable"><div class="tab _{len(tabs)}">{knoppen}</div>{inhoud}</div></div></body></html>')
_li = lambda *rows: "<ul>" + "".join(f"<li> {l} <span>{t} uur</span> </li>" for l, t in rows) + "</ul>"
_onbekend = '<p class="txt-white">Tijden nog niet bekend</p>'
afas_agenda = "<html><body>" + "".join([
    _afas_rij("good-charlotte", "Good Charlotte", f"maandag 16 november {j}"),
    _afas_rij("bloc-party-interpol", "Bloc Party + Interpol", f"dinsdag 17 november {j}"),
    _afas_rij("de-mega-sint-show", "De Mega Sint Show", f"woensdag 25 november {j}", "13:45"),
    _afas_rij("de-mega-sint-show", "De Mega Sint Show", f"woensdag 25 november {j}", "16:45", "alt st-soldout"),
    _afas_rij("beth-hart", "Beth Hart", f"dinsdag 01 december {j}"),
    _afas_rij("beth-hart", "Beth Hart", f"vrijdag 04 december {j}", klasse="alt st-none"),
    _afas_rij("vieze-asbak", "Vieze Asbak All Day Long", f"zaterdag 05 december {j}", klasse="st-soldout"),
    _afas_rij("freek-vonk", "Freek Vonk Live", f"zaterdag 19 december {j}", "10:00"),
    _afas_rij("freek-vonk", "Freek Vonk Live", f"zaterdag 19 december {j}", "13:30"),
    _afas_rij("masego", "Masego", f"dinsdag 23 februari {j + 1}", klasse="st-moved"),
    _afas_rij("brandi-carlile", "Brandi Carlile", f"vrijdag 02 april {j + 1}", klasse="st-moved", extra=f"<span class=\"old\">dinsdag 27 oktober {j}</span> "),
    _afas_rij("stuk", "Pagina Stuk", f"zondag 04 juli {j + 1}"),
    _afas_rij("geweest", "Al Geweest", "zondag 04 juli 2021")]) + "</body></html>"
afas_paginas = {
    "https://www.afaslive.nl/agenda": afas_agenda,
    "https://www.afaslive.nl/agenda/good-charlotte": _afas_pagina([_afas_blok("Good Charlotte", f"maandag 16 november {j}", prijzen_="<li>Entree vanaf<span>€ 64,52</span></li>")],
        [("ma. 16 nov.", _li(("Deuren Open", "18:30"), ("Aanvang Opener: Grave Secrets", "19:00"), ("Aanvang Special guest: Yellowcard", "19:45"), ("Aanvang: Good Charlotte", "21:05"), ("Verwacht einde show", "22:35")))],
        '<li><i></i> Special Guest <a href="#">Yellowcard</a></li><li><i></i> Special Guest <a href="#">Grave Secrets</a></li>'),
    "https://www.afaslive.nl/agenda/bloc-party-interpol": _afas_pagina([_afas_blok("Bloc Party + Interpol", f"dinsdag 17 november {j}")],
        [("di. 17 nov.", _li(("Deuren open", "18:00"), ("Aanvang Support: Heartworms", "18:45"), ("Aanvang: Interpol", "19:45"), ("Aanvang: Bloc Party", "21:30"), ("Verwacht einde", "22:45")))]),
    "https://www.afaslive.nl/agenda/de-mega-sint-show": _afas_pagina(
        [_afas_blok("De Mega Sint Show", f"woensdag 25 november {j}", "13:45", "<li>Droomplaatsen<span>€ 37,-</span></li><li>Rang 2<span>€ 22,-</span></li>"),
         _afas_blok("De Mega Sint Show", f"woensdag 25 november {j}", "16:45", "<li>Rang 1<span>€ 32,-</span></li>")],
        [("wo. 25 nov.<br/>13:45", _li(("Deuren open", "13:45"))), ("wo. 25 nov.<br/>16:45", _li(("Deuren open", "16:45")))]),
    "https://www.afaslive.nl/agenda/beth-hart": _afas_pagina([_afas_blok("Beth Hart", f"dinsdag 1 december {j}", "20:00"), _afas_blok("Beth Hart", f"vrijdag 4 december {j}", "20:00")],
        [("di. 01 dec.<br/>20:00", _onbekend), ("vr. 04 dec.<br/>20:00", "<ul> </ul>")],
        '<li><i></i> Support act <a href="#">Emmy d’Arc</a></li><li><i></i> Support act <a href="#">JEN</a></li>'),
    "https://www.afaslive.nl/agenda/vieze-asbak": _afas_pagina([_afas_blok("Vieze Asbak", f"zaterdag 5 december {j}", prijzen_="")],
        [("za. 05 dec.", _li(("Verwachtte eindtijd", "00:00"), ("Deuren open", "17:00")))]),
    "https://www.afaslive.nl/agenda/freek-vonk": _afas_pagina([_afas_blok("Freek Vonk Live", f"zaterdag 19 december {j}", "10:00"), _afas_blok("Freek Vonk Live", f"zaterdag 19 december {j}", "13:30")],
        [("za. 19 dec.<br/>10:00", _li(("Aanvang", "10:00"))), ("za. 19 dec.<br/>13:30", _li(("Aanvang", "10:00")))]),
    "https://www.afaslive.nl/agenda/masego": _afas_pagina([_afas_blok("Masego", f"dinsdag 23 februari {j + 1}")], [("di. 23 feb.", _onbekend)]),
    "https://www.afaslive.nl/agenda/brandi-carlile": _afas_pagina([_afas_blok("Brandi Carlile", f"vrijdag 2 april {j + 1}")], [("vr. 02 apr.", _li(("Aanvang show", "20:30"), ("Pauze", "21:15")))]),
}
class _FA:
    def __init__(self, pages): self.pages, self.stats, self.n = pages, {}, 0
    def get(self, url):
        self.n += 1
        return self.pages.get(url)
afas_src = {"name": "AFAS Live", "agenda_url": "https://www.afaslive.nl/agenda", "platform": "afaslive"}
afas_cache, fa = {}, _FA(afas_paginas)
ae = venues.scrape(afas_src, fa, {}, lambda *a: None, afas_cache)
kort = lambda t, d: next(({k: e.get(k) for k in ("time", "doors", "start", "support", "tot", "price", "status")} for e in ae if e["title"] == t and e["date"] == d), None)
check("afas: één item per speeldatum, kale namen, verleden niet", [(e["title"], e["date"], e["time"]) for e in ae],
      [("Good Charlotte", f"{j}-11-16", "19:00"), ("Bloc Party + Interpol", f"{j}-11-17", "18:45"), ("De Mega Sint Show", f"{j}-11-25", "13:45"), ("De Mega Sint Show", f"{j}-11-25", "16:45"),
       ("Beth Hart", f"{j}-12-01", "20:00"), ("Beth Hart", f"{j}-12-04", "20:00"), ("Vieze Asbak All Day Long", f"{j}-12-05", "17:00"), ("Freek Vonk Live", f"{j}-12-19", "10:00"),
       ("Freek Vonk Live", f"{j}-12-19", "13:30"), ("Masego", f"{j + 1}-02-23", None), ("Brandi Carlile", f"{j + 1}-04-02", "20:30"), ("Pagina Stuk", f"{j + 1}-07-04", None)])
check("afas: tijdschema onderaan (deuren, voorprogramma's, hoofdact, einde) en prijs; niet de 10:00 van de voorverkoop", kort("Good Charlotte", f"{j}-11-16"),
      {"time": "19:00", "doors": "18:30", "start": "21:05", "support": ["Grave Secrets", "Yellowcard"], "tot": "22:35", "price": 64.52, "status": None})
check("afas: blokken per act", next(e["times"] for e in ae if e["title"] == "Good Charlotte"),
      [{"a": "Grave Secrets", "s": "19:00"}, {"a": "Yellowcard", "s": "19:45"}, {"a": "Good Charlotte", "s": "21:05"}])
check("afas: twee hoofdacts: aanvang is de eerste, support alleen wat ervoor komt", kort("Bloc Party + Interpol", f"{j}-11-17"),
      {"time": "18:45", "doors": "18:00", "start": "19:45", "support": ["Heartworms"], "tot": "22:45", "price": 78.54, "status": None})
check("afas: twee shows op één dag, elk hun tijd, prijs en uitverkocht", (kort("De Mega Sint Show", f"{j}-11-25"), [(e["time"], e.get("doors"), e.get("price"), e.get("status")) for e in ae if e["title"] == "De Mega Sint Show"]),
      ({"time": "13:45", "doors": "13:45", "start": None, "support": None, "tot": None, "price": 22.0, "status": None}, [("13:45", "13:45", 22.0, None), ("16:45", "16:45", 32.0, "sold")]))
check("afas: tijden nog niet bekend: aanvang uit het datumblok, voorprogramma van boven aan de pagina", kort("Beth Hart", f"{j}-12-01"),
      {"time": "20:00", "doors": None, "start": None, "support": ["Emmy d’Arc", "JEN"], "tot": None, "price": 78.54, "status": None})
check("afas: eindtijd boven deuren open, uitverkocht", kort("Vieze Asbak All Day Long", f"{j}-12-05"),
      {"time": "17:00", "doors": "17:00", "start": None, "support": None, "tot": "00:00", "price": None, "status": "sold"})
check("afas: schema dat eerder begint dan de tweede show van de dag telt niet", [(e["time"], e.get("start"), e.get("times")) for e in ae if e["title"] == "Freek Vonk Live"],
      [("10:00", "10:00", [{"a": "Freek Vonk Live", "s": "10:00"}]), ("13:30", None, None)])
check("afas: verplaatst: de nieuwe datum; 'Aanvang show' is de hoofdact, pauze telt niet", (kort("Brandi Carlile", f"{j + 1}-04-02")["start"], next(e["times"] for e in ae if e["title"] == "Brandi Carlile")),
      ("20:30", [{"a": "Brandi Carlile", "s": "20:30"}]))
check("afas: 'Very Special Guest Pendulum' boven aan de pagina -> 'Pendulum'",
      venues.afas_detail(BeautifulSoup('<ul class="act"><li><i></i> Very Special Guest <a>Pendulum</a></li><li>Support act: TBA</li></ul>', "html.parser"))["support"], ["Pendulum"])
check("afas: pagina niet gekregen: de show blijft staan met wat de agenda geeft", kort("Pagina Stuk", f"{j + 1}-07-04"),
      {"time": None, "doors": None, "start": None, "support": None, "tot": None, "price": None, "status": None})
n1 = fa.n
ae2 = venues.scrape(afas_src, fa, {}, lambda *a: None, afas_cache)
check("afas: tweede keer uit de cache (alleen de agenda en de pagina die mislukte opnieuw), zelfde uitkomst", (fa.n - n1, ae2 == ae), (2, True))
try:
    venues.scrape(afas_src, _FA({}), {}, lambda *a: None, {})
    fout_afas = None
except RuntimeError as ex:
    fout_afas = "fout"
check("afas: agenda niet gekregen -> fout (geen terugval op de gewone uitlezer, oude items blijven)", fout_afas, "fout")
check("afas: staat als platform bij de bron", next(b.get("platform") for b in json.loads((sources.ROOT / "scraper/bronnen.json").read_text(encoding="utf-8")) if b["name"] == "AFAS Live"), "afaslive")
s_tot, _ = scrape.schoon.schoon_alles({"updated": "x", "venues": {"cds": dict(VN["cds"], prov="NB")}, "events": [
    {"id": "e1", "v": "cds", "title": "A", "date": f"{j}-11-04", "time": "20:30", "url": "https://c.nl", "tot": "22:35"},
    {"id": "e2", "v": "cds", "title": "B", "date": f"{j}-11-04", "time": "20:30", "url": "https://c.nl", "tot": "laat"}]})
check("opschonen: eindtijd 'tot' blijft alleen als het een tijd is", [e.get("tot") for e in s_tot["events"]], ["22:35", None])

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)")); sys.exit(1 if fouten else 0)
