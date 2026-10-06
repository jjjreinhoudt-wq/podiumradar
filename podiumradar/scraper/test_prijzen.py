"""Tests voor de prijsherkenning (scraper/prijzen.py en de koppeling in sources.py).

Draaien:  python scraper/test_prijzen.py      (geen internet nodig)
"""
import datetime as dt, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bs4 import BeautifulSoup
import prijzen, sources

DAG = (dt.date.today() + dt.timedelta(days=20)).isoformat()
fouten = 0


def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht and type(kreeg) is type(verwacht)
    fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))


def ld(offers, **extra):
    return dict({"@type": "MusicEvent", "name": "Test", "startDate": DAG + "T20:00", "offers": offers}, **extra)


# --- JSON-LD offers
check("offer met getal", prijzen.from_offers(ld({"@type": "Offer", "price": 24.5, "priceCurrency": "EUR"})), 24.5)
check("offer met komma-string", prijzen.from_offers(ld({"price": "24,50"})), 24.5)
check("offer met euroteken", prijzen.from_offers(ld({"price": "€ 19,-"})), 19)
check("lijst van offers: laagste", prijzen.from_offers(ld([{"price": "32.50"}, {"price": "27.50"}, {"price": 45}])), 27.5)
check("AggregateOffer lowPrice", prijzen.from_offers(ld({"@type": "AggregateOffer", "lowPrice": "15", "highPrice": "35"})), 15)
check("geneste offers", prijzen.from_offers(ld({"@type": "AggregateOffer", "offers": [{"price": 22}, {"price": 18}]})), 18)
check("servicekosten tellen niet", prijzen.from_offers(ld([{"name": "Servicekosten", "price": 2.5}, {"name": "Regulier", "price": 30}])), 30)
check("price 0 zonder 'gratis' = onbekend", prijzen.from_offers(ld({"price": "0"})), None)
check("price 0 met 'gratis'", prijzen.from_offers(ld({"name": "Gratis toegang", "price": 0})), 0)
check("isAccessibleForFree", prijzen.from_offers(ld(None, isAccessibleForFree=True)), 0)
check("andere munt", prijzen.from_offers(ld({"price": 30, "priceCurrency": "GBP"})), None)
check("onzin-prijs", prijzen.from_offers(ld({"price": "zie website"})), None)
check("geen offers", prijzen.from_offers(ld(None)), None)

# --- tekst
check("Entree: € 24,50", prijzen.from_text("Datum 12 okt\nEntree: € 24,50\nAanvang 20:00"), 24.5)
check("Tickets vanaf €19,-", prijzen.from_text("Tickets vanaf €19,- excl. servicekosten"), 19)
check("Prijs 15 euro", prijzen.from_text("Prijs 15 euro"), 15)
check("los bedrag, enige op de pagina", prijzen.from_text("Za 12 okt 20:00\n€ 24,50\nKoop tickets"), 24.5)
check("losse bedragen, meerdere: onzeker", prijzen.from_text("€ 24,50\n€ 12,00\n€ 30,00"), None)
check("Entree: gratis", prijzen.from_text("Aanvang 15:00\nEntree: gratis"), 0)
check("Gratis toegang", prijzen.from_text("Gratis toegang, vol = vol"), 0)
check("vrij entree", prijzen.from_text("Het concert is vrij entree."), 0)
check("toegang vrij", prijzen.from_text("Toegang vrij"), 0)
check("gratis voor museumkaarthouders: geen 'gratis'", prijzen.from_text("Gratis toegang voor Museumkaarthouders"), None)
check("kinderen gratis, wel bedrag", prijzen.from_text("Entree € 15, kinderen gratis"), 15)
check("alleen servicekosten", prijzen.from_text("Servicekosten € 2,50 per bestelling"), None)
check("geen prijs", prijzen.from_text("Za 12 okt, aanvang 20:00. Een avond vol muziek."), None)
check("bedrag(1.250,00)", prijzen.bedrag("1.250,00"), 1250.0)

# --- via sources.from_jsonld / from_text (zoals de scraper het doet)
html = ('<html><head><script type="application/ld+json">' + json.dumps(ld([{"price": "27,50"}, {"price": "22,50"}]))
        + "</script></head><body></body></html>")
evs = [sources.from_jsonld(o, "https://x.nl/agenda/test") for o in sources.jsonld_events(BeautifulSoup(html, "html.parser"))]
check("from_jsonld zet price", evs[0].get("price"), 22.5)
evs = [sources.from_jsonld(o, "https://x.nl/a/t") for o in sources.jsonld_events(BeautifulSoup(
    html.replace('"27,50"', '"zie site"').replace('"22,50"', '"zie site"'), "html.parser"))]
check("from_jsonld zonder prijs: geen veld", "price" in evs[0], False)

# PaRaDoX-achtig: blok 'meer concerten' met andere datums en prijzen wordt eerst verwijderd
d = dt.date.today() + dt.timedelta(days=10)
pagina = f"""<html><body><main><h1>Kwartet X</h1><p>{d.day} {['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec'][d.month-1]} {d.year}</p>
<p>Aanvang 20:30</p><p>Entree € 12,50</p>
<div class="more-events"><a href="/a">Ander concert</a><p>1 jan 2027 21:00 Entree € 8,00</p></div></main></body></html>"""
ev = sources.from_text(BeautifulSoup(pagina, "html.parser"), "https://paradox.nl/agenda/kwartet-x")
check("from_text: prijs van de voorstelling zelf", ev.get("price"), 12.5)
pagina2 = pagina.replace("<p>Entree € 12,50</p>", "")
ev = sources.from_text(BeautifulSoup(pagina2, "html.parser"), "https://paradox.nl/agenda/kwartet-x")
check("from_text: geen prijs uit 'meer concerten'", "price" in ev, False)
ev = sources.from_text(BeautifulSoup(pagina2.replace("<p>Aanvang 20:30</p>", "<p>Aanvang 20:30</p><p>Entree: gratis</p>"),
                                     "html.parser"), "https://paradox.nl/agenda/kwartet-x")
check("from_text: gratis", ev.get("price"), 0)

print("\n" + ("Alle tests geslaagd." if not fouten else f"{fouten} test(s) mislukt."))
sys.exit(1 if fouten else 0)
