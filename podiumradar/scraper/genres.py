"""Genres van bekende artiesten en voorstellingen (scraper/genres_bekend.json).

De sites van podia geven zelden een genre mee; trefwoorden in de titel ('tribute', 'musical') vangen maar een klein deel.
Daarom staat in genres_bekend.json per artiest of voorstelling een genre, met de hand (door Claude) ingevuld voor namen
die herkend zijn. Wat er niet in staat, blijft bij de gok op trefwoorden of het standaardgenre van het soort podium.

Sleutel = de titel in kleine letters zonder accenten en leestekens; eerst de hele titel, dan het deel vóór ' - '
('Pieter Derks - Ja, leuk' -> 'pieterderksjaleuk', daarna 'pieterderks'). Aanvullen: gewoon regels toevoegen of
verbeteren in genres_bekend.json (ongeldige JSON = geen bekende genres, de run gaat door).
"""
import json, pathlib, re, unicodedata

PAD = pathlib.Path(__file__).resolve().parent / "genres_bekend.json"
# Genres die de app kent; iets anders in het bestand wordt genegeerd
TOEGESTAAN = {"Pop", "Rock", "Indie", "Metal", "Punk", "Hiphop", "Dance", "Jazz", "Soul/Funk", "Blues", "Folk/Americana",
              "Wereld", "Nederlandstalig", "Singer-songwriter", "Klassiek", "Tribute", "Feest", "Cabaret", "Lezing", "Jeugd",
              "Toneel", "Musical", "Dans", "Opera", "Muziektheater", "Show", "Circus"}


def sleutel(naam):
    n = unicodedata.normalize("NFD", str(naam).lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in n if unicodedata.category(c) != "Mn"))


def kop(titel):
    """Het deel van de titel dat de artiest of de voorstelling noemt (vóór ' ✦ ' en vóór ' - ')."""
    t = re.sub(r"\s*\((festival|festival, dag \d)\)$", "", str(titel), flags=re.I).split(" ✦ ")[0]
    return t.split(" - ")[0].strip()


def laad(pad=PAD):
    try:
        ruw = json.loads(pathlib.Path(pad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: g for k, g in ruw.items() if isinstance(k, str) and g in TOEGESTAAN} if isinstance(ruw, dict) else {}


BEKEND = laad()


def bekend_genre(titel, bekend=None):
    """Genre uit genres_bekend.json, of None als de titel er niet in staat."""
    b = BEKEND if bekend is None else bekend
    return b.get(sleutel(titel)) or b.get(sleutel(kop(titel)))


if __name__ == "__main__":
    # python scraper/genres.py  -> namen in site/data.json die nog geen echt genre hebben (sleutel, titel, podium), meest gespeeld eerst.
    # Daarmee vul je genres_bekend.json aan; draai daarna `python scraper/scrape.py --reclassify`.
    import collections
    data = json.loads((PAD.parent.parent / "site/data.json").read_text(encoding="utf-8"))
    V, telling, vb = data["venues"], collections.Counter(), {}
    for e in data["events"]:
        v = V.get(e["v"], {})
        if e.get("genre") not in ("Overig", "Theater"):
            continue
        k = sleutel(e["title"]) if v.get("type") == "thea" else sleutel(kop(e["title"]))
        if len(k) >= 2 and k not in BEKEND:
            telling[k] += 1
            vb.setdefault(k, (e["title"], f"{v.get('name', '')}, {v.get('city', '')}"))
    for k, n in telling.most_common():
        print(f"{k}\t{vb[k][0]}\t{vb[k][1]}\t{n}x")
