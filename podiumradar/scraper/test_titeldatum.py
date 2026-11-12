"""Datum in de titel ('Focus ✦ do 18 feb ✦ Luxor Live'): titel_datum() en de toepassing in scrape_source(), zonder internet.
Draaien:  python scraper/test_titeldatum.py"""
import datetime as dt, pathlib, sys

HIER = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import sources

fouten = 0
def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht; fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))

NU = dt.date(2026, 11, 12)   # donderdag
td = lambda t: sources.titel_datum(t, NU)
check("✦ datum ✦ zaal, volgend jaar", td("Focus ✦ do 18 feb ✦ Luxor Live"), ("Focus", dt.date(2027, 2, 18)))
check("✦ datum ✦ zaal, dit jaar", td("Anneke van Giersbergen ✦ zo 15 nov ✦ Luxor Live"), ("Anneke van Giersbergen", dt.date(2026, 11, 15)))
check("met jaartal", td("Laurence Jones ✦ do 11 nov 2027 ✦ Luxor Live"), ("Laurence Jones", dt.date(2027, 11, 11)))
check("streepje en datum achteraan", td("Femxle Frontier - vr 22 jan"), ("Femxle Frontier", dt.date(2027, 1, 22)))
check("hele weekdag", td("Quiz'm Top 2000 ✦ woensdag 23 december ✦ Luxor Live"), ("Quiz'm Top 2000", dt.date(2026, 12, 23)))
check("& in de naam blijft", td("Robben Ford meets Licks & Brains ✦ zo 14 mrt ✦ Luxor Live")[0], "Robben Ford meets Licks & Brains")
check("weekdag klopt niet: niets doen", td("Focus ✦ ma 18 feb ✦ Luxor Live"), ("Focus ✦ ma 18 feb ✦ Luxor Live", None))
check("datum met jaartal al voorbij: niets doen", td("Oud ✦ do 12 nov 2025 ✦ Zaal")[1], None)
check("geen weekdag: niets doen", td("Tribute - 22 jan")[1], None)
check("gewone titel", td("Maria 3 mei"), ("Maria 3 mei", None))
check("woord dat op een weekdag lijkt", td("Avond - Dolly 3 mei")[1], None)
check("alleen een datum, geen naam", td("✦ do 18 feb ✦ Luxor Live")[1], None)
check("onmogelijke datum", td("Iets ✦ za 31 feb ✦ Zaal")[1], None)
check("lege titel", sources.titel_datum("", NU), ("", None))

# Toepassing: scrape_source met een bron waarvan de voorstellingspagina's al in de cache staan (geen netwerk nodig)
sources.TODAY = NU
class GeenNet:
    def get(self, u): return '<html><body><a href="/agenda/focus-2/">x</a><a href="/agenda/anneke/">y</a><a href="/agenda/gewoon/">z</a><a href="/agenda/reeks/">r</a></body></html>' if u.endswith("/agenda") else None
    def allowed(self, u): return True
    def __getattr__(self, n): return lambda *a, **k: None
src = {"name": "Luxor Live", "city": "Arnhem", "prov": "Gelderland", "type": "pop", "agenda_url": "https://www.luxorlive.nl/agenda"}
B = "https://www.luxorlive.nl/agenda/"
ev = lambda slug, date, title, **x: {"at": NU.isoformat(), "v": sources.CACHE_V, "ev": dict({"date": date, "time": "19:45", "title": title, "url": B + slug + "/"}, **x)}
cache = {B + "focus-2/": ev("focus-2", "2027-01-01", "Focus ✦ do 18 feb ✦ Luxor Live"),
         B + "anneke/": ev("anneke", "2027-03-27", "Anneke van Giersbergen ✦ zo 15 nov ✦ Luxor Live"),
         B + "gewoon/": ev("gewoon", "2026-12-05", "Gewone Band"),
         B + "reeks/": ev("reeks", "2026-12-01", "Expo ✦ do 18 feb ✦ Luxor Live", end="2027-03-01")}
try:
    uit = {e["url"].rstrip("/").rsplit("/", 1)[1]: e for e in sources.scrape_source(src, GeenNet(), cache, {"detail_refresh_days": 7}, lambda *a: None)}
except Exception as ex:  # de bron wordt in deze test nagebootst; lukt dat niet meer, dan faalt de test duidelijk
    uit = {}; print("FOUT scrape_source:", repr(ex)); fouten += 1
check("bron: datum uit de titel", (uit.get("focus-2") or {}).get("date"), "2027-02-18")
check("bron: titel is de kale naam", (uit.get("focus-2") or {}).get("title"), "Focus")
check("bron: show van zondag staat op zondag", (uit.get("anneke") or {}).get("date"), "2026-11-15")
check("bron: gewone titel ongemoeid", ((uit.get("gewoon") or {}).get("date"), (uit.get("gewoon") or {}).get("title")), ("2026-12-05", "Gewone Band"))
check("bron: periode houdt zijn begindatum", ((uit.get("reeks") or {}).get("date"), (uit.get("reeks") or {}).get("title")), ("2026-12-01", "Expo"))

print("\nALLES GOED" if not fouten else f"\n{fouten} FOUT(EN)")
sys.exit(1 if fouten else 0)
