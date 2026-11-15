"""Test voor de bekende genres (scraper/genres.py en de plek in scrape.py waar ze gebruikt worden).  python scraper/test_genres.py"""
import json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.argv = [sys.argv[0]]
import genres, scrape

fouten = 0


def check(naam, ok, extra=None):
    global fouten
    fouten += 0 if ok else 1
    print(("ok   " if ok else "FOUT ") + naam + ("" if ok or extra is None else f" -> {extra!r}"))


B = {"pieterderks": "Cabaret", "babyreindeer": "Toneel", "cultofluna": "Metal", "verzonnen": "Bestaatniet"}
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "g.json"
    p.write_text(json.dumps(B), encoding="utf-8")
    geladen = genres.laad(p)
    check("laden: onbekend genre wordt genegeerd", "verzonnen" not in geladen and geladen["cultofluna"] == "Metal", geladen)
    p.write_text("{kapot", encoding="utf-8")
    check("laden: kapot bestand geeft een lege lijst, geen fout", genres.laad(p) == {})
    check("laden: ontbrekend bestand geeft een lege lijst", genres.laad(pathlib.Path(d) / "nee.json") == {})

check("sleutel: accenten, hoofdletters en leestekens weg", genres.sleutel("Queensrÿche & Ço.!") == "queensrycheco")
check("hele titel", genres.bekend_genre("Cult of Luna", geladen) == "Metal")
check("deel voor het streepje", genres.bekend_genre("Pieter Derks - Ja, leuk (reprise)", geladen) == "Cabaret")
check("datum en zaal achter de naam tellen niet mee", genres.bekend_genre("Cult Of Luna ✦ do 18 feb ✦ Grote zaal", geladen) == "Metal")
check("onbekend blijft onbekend", genres.bekend_genre("Lokale Band Zonder Naam", geladen) is None)

echt = genres.laad()
check("genres_bekend.json: geldig en gevuld", len(echt) > 1000, len(echt))
check("genres_bekend.json: alleen toegestane genres", set(echt.values()) <= genres.TOEGESTAAN)

oud, genres.BEKEND = genres.BEKEND, geladen
try:
    check("scrape: bekende naam wint van het standaardgenre", scrape.guess_genre("Cult of Luna", "pop") == "Metal")
    check("scrape: bekende naam wint van een trefwoord in de titel", scrape.guess_genre("Pieter Derks - Theater van de lach", "thea") == "Cabaret")
    check("scrape: Jeugd uit de titel wint altijd", scrape.guess_genre("Pieter Derks - Familievoorstelling (4+)", "thea") == "Jeugd")
    check("scrape: onbekend zonder trefwoord krijgt het standaardgenre", scrape.guess_genre("Lokale Band", "pop") == "Overig")
    check("scrape: onbekend met trefwoord houdt het trefwoord", scrape.guess_genre("Lokale Band - Pink Floyd tribute", "pop") == "Tribute")
finally:
    genres.BEKEND = oud

print("\n" + (f"{fouten} FOUT(EN)" if fouten else "ALLES GOED"))
sys.exit(1 if fouten else 0)
