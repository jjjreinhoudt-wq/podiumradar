"""Spotify: welke artiesten staan op Spotify? Draait na de nachtelijke ophaalronde (update.yml).

Per artiest wordt één keer opgezocht (Spotify Web API, zoeken op artiestnaam) en onthouden:
  gevonden       -> de knop in de app opent direct de artiestenpagina
  niet gevonden  -> de knop in de app is grijs
  nog niet gezocht ('pending') -> de app toont een gewone zoeklink
Zonder sleutels (secrets SPOTIFY_CLIENT_ID en SPOTIFY_CLIENT_SECRET) doet dit script niets nieuws; wat al
opgezocht is blijft staan. Het eigenaarsaccount van de Spotify-app moet Premium hebben (regel van Spotify
sinds februari 2026); valt dat weg, dan stopt het opzoeken en blijven de bekende uitkomsten gewoon staan.

Alleen een EXACTE naamsovereenkomst telt (zonder hoofdletters, accenten en leestekens, "The" vooraan mag
verschillen): liever een grijze knop dan de verkeerde artiest. Bij meerdere treffers wint de populairste.
Handmatig corrigeren kan in scraper/spotify_overrides.json:
  {"<artiestsleutel>": "<22 tekens Spotify-id>"}  forceert dat artiestenpagina
  {"<artiestsleutel>": null}                       forceert grijs (niet op Spotify)
  {"<artiestsleutel>": "skip"}                     toon geen Spotify-knop
De artiestsleutel is dezelfde als in de app (zie key() in meldingen.py); hij staat in site/spotify.json.

Bestanden:
  scraper/spotify_cache.json  {"v":1,"artists":{sleutel: {"id": id of null, "t": datum van opzoeken}}}
  site/spotify.json           {"v":1,"updated":datum,"found":{sleutel: id},"none":[sleutel],"pending":[sleutel]}
                              (alleen artiesten waarbij de app een Spotify-knop toont)
Opgeslagen wordt alleen het Spotify-id en of het gevonden is, geen namen, plaatjes of andere gegevens.

Gebruik:  python scraper/spotify.py [--max-minuten 15] [--max-verzoeken 2500] [--droog]
          --droog: alleen tellen wat er opgezocht zou worden, niets versturen of schrijven
Test:     python scraper/test_spotify.py   (geen internet nodig)
"""
import argparse, datetime as dt, json, os, pathlib, re, sys, time
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from meldingen import key, acts  # zelfde artiestsleutel en artiestnaam als de app

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "site/data.json"
CACHE = ROOT / "scraper/spotify_cache.json"
OVERRIDES = ROOT / "scraper/spotify_overrides.json"
OUT = ROOT / "site/spotify.json"

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
OPNIEUW_NIET_GEVONDEN = 30   # dagen voordat een 'niet gevonden' opnieuw wordt geprobeerd
BEWAAR_DAGEN = 400           # oude cache-items die nergens meer voorkomen worden opgeruimd
PAUZE = 0.4                  # seconden tussen zoekopdrachten

# Zelfde indeling als app.js (type per item), zodat de app en dit script het eens zijn over wat een artiest is
THEATER_GENRES = {"Cabaret", "Comedy", "Musical", "Toneel", "Dans", "Opera", "Theater", "Jeugd"}
TYPE_OF = {"thea": "thea", "film": "film", "museum": "expo", "festival": "fest"}
ARTIEST_GENRES = {"Cabaret", "Comedy"}   # de titel is de naam van de cabaretier of comedian
GEEN_MUZIEK = {"Feest", "Lezing"}
NOT_MUSIC = re.compile(r"workshop|lezing|cursus|quiz|bingo|borrel|lunch|diner|rondleiding|open dag|proefles|clinic|"
                       r"filmavond|tentoonstelling|expositie|vergadering|netwerk", re.I)


class Gestopt(Exception):
    """Spotify laat niet meer toe (quotum, Premium verlopen, geen toegang): stoppen, bekende uitkomsten blijven."""


def event_type(e, v):
    g, vt = e.get("genre"), (v or {}).get("type")
    if g == "Film" and vt != "festival":
        return "film"
    if g == "Tentoonstelling" and vt != "festival":
        return "expo"
    return TYPE_OF.get(vt) or ("thea" if g in THEATER_GENRES else "pop")


def eligible(e, v):
    """Toont de app bij dit item een Spotify-knop? (zelfde regel als de zoeklink in app.js, plus cabaret/comedy)"""
    if str(e.get("id", ""))[:1] == "f":      # festivalitems: de naam is het festival
        return False
    t, g = event_type(e, v), e.get("genre")
    if t in ("film", "expo", "fest"):
        return False
    if g in ARTIEST_GENRES:
        return True
    return t == "pop" and g not in GEEN_MUZIEK and not NOT_MUSIC.search(e.get("title", ""))


def artiesten(data):
    """{sleutel: {'naam': ..., 'eerste': vroegste datum}} voor alle items waar een Spotify-knop bij hoort."""
    out = {}
    for e in data["events"]:
        if not eligible(e, data["venues"].get(e.get("v"))):
            continue
        namen = acts(e)
        naam = (namen[0] if namen else "").strip()
        k = key(naam)
        if len(k) < 3:
            continue
        a = out.setdefault(k, {"naam": naam, "eerste": e["date"]})
        a["eerste"] = min(a["eerste"], e["date"])
    return out


SCHEIDERS = re.compile(r"\s+[✦•|/–—]\s+|\s+-\s+")   # " ✦ ", " • ", " | ", " / ", " – ": daarna volgt datum, zaal of een andere act


def varianten(naam):
    """Zoeknamen, van volledig naar vooral de artiest zelf:
    de hele naam; zonder (NL)/(18+) achteraan; het deel voor ' ✦ ', ' • ', ' | ' of ' / ';
    bij 'Reeks: Artiest' of 'Artiest: Show' het deel voor en het deel na de dubbele punt.
    Nooit gesplitst op '&' of ',': dat zijn vaak duo's of groepsnamen. Alleen een exacte treffer telt toch."""
    n = naam.strip()
    zonder = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    eerste = SCHEIDERS.split(zonder)[0].strip()
    kandidaten = [(n, 3), (zonder, 3), (eerste, 4)]
    if ":" in eerste:
        voor, na = eerste.split(":", 1)
        kandidaten += [(voor.strip(), 4), (na.strip(), 4)]
    uniek = []
    for tekst, minimaal in kandidaten:
        if len(key(tekst)) >= minimaal and tekst not in uniek:
            uniek.append(tekst)
    return uniek


def vergelijk(s):
    """Sleutel om namen te vergelijken: zonder hoofdletters/accenten/leestekens, '&' en '+' gelijk aan 'en'/'and',
    en 'The' vooraan telt niet mee."""
    t = re.sub(r"[&+]", " and ", (s or "").lower())
    k = key(" ".join(w for w in re.split(r"\s+", t) if w not in ("and", "en")))
    return k[3:] if k.startswith("the") and len(k) > 6 else k


def zelfde_naam(gevraagd, gevonden):
    a = vergelijk(gevraagd)
    return bool(a) and a == vergelijk(gevonden)


def kies(naam, kandidaten):
    """Beste exacte treffer (populairste), of None."""
    goed = [c for c in kandidaten if c and ID_RE.match(str(c.get("id", ""))) and zelfde_naam(naam, c.get("name", ""))]
    if not goed:
        return None
    return max(goed, key=lambda c: c.get("popularity") or 0)["id"]


class Spotify:
    """Dunne laag om de Spotify Web API (client credentials). Geheimen worden nooit geprint."""

    def __init__(self, cid, secret, sessie=None, slaap=time.sleep):
        self.cid, self.secret = cid, secret
        self.s = sessie or requests.Session()
        self.slaap = slaap
        self.tok = None
        self.verzoeken = 0

    def _token(self):
        r = self.s.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=(self.cid, self.secret), timeout=30)
        if r.status_code in (400, 401):
            raise Gestopt("Spotify weigert de sleutels (controleer SPOTIFY_CLIENT_ID en SPOTIFY_CLIENT_SECRET)")
        r.raise_for_status()
        self.tok = r.json()["access_token"]

    def zoek(self, naam):
        """Lijst artiesten [{'id','name','popularity'}] bij deze naam."""
        for poging in range(5):
            if not self.tok:
                self._token()
            self.verzoeken += 1
            r = self.s.get(SEARCH_URL, params={"q": naam, "type": "artist", "limit": 10, "market": "NL"},
                           headers={"Authorization": "Bearer " + self.tok}, timeout=30)
            if r.status_code == 401:            # token verlopen
                self.tok = None
                continue
            if r.status_code == 403:
                raise Gestopt("Spotify geeft geen toegang (403): heeft het account dat de app beheert nog Premium?")
            if r.status_code == 429:
                try:
                    wacht = float(r.headers.get("Retry-After") or 5)
                except ValueError:
                    wacht = 5.0
                reden = ""
                try:
                    reden = str((r.json() or {}).get("reason") or "")
                except Exception:
                    pass
                if wacht > 120 or "QUOTA" in reden.upper():
                    raise Gestopt(f"Spotify-quotum bereikt (wacht {int(wacht)} s): morgen verder")
                self.slaap(wacht + 1)
                continue
            if r.status_code >= 500:
                self.slaap(2 ** poging)
                continue
            r.raise_for_status()
            return (r.json().get("artists") or {}).get("items") or []
        raise requests.RequestException("Spotify gaf na meerdere pogingen geen antwoord")


def laad(pad, standaard):
    try:
        return json.loads(pathlib.Path(pad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return standaard


def nodig(cache, k, vandaag):
    """Moet deze artiest (opnieuw) worden opgezocht?"""
    c = cache.get(k)
    if not c:
        return True
    if c.get("id"):
        return False
    try:
        return (vandaag - dt.date.fromisoformat(c["t"])).days >= OPNIEUW_NIET_GEVONDEN
    except (KeyError, ValueError, TypeError):
        return True


def zoek_op(client, naam, slaap=time.sleep):
    """Id van de artiest op Spotify, of None; probeert de naamvarianten (met pauze ertussen)."""
    for i, v in enumerate(varianten(naam)):
        if i:
            slaap(PAUZE)
        gevonden = kies(v, client.zoek(v))
        if gevonden:
            return gevonden
    return None


def publiceer(arts, cache, overrides, vandaag):
    """Maakt de inhoud van site/spotify.json."""
    found, none, pending = {}, [], []
    for k in sorted(arts):
        o = overrides.get(k, "geen") if isinstance(overrides, dict) else "geen"
        if o == "skip":
            continue
        if o != "geen":                           # id of null uit de overrides
            if o and ID_RE.match(str(o)):
                found[k] = o
            else:
                none.append(k)
            continue
        c = cache.get(k)
        if not c:
            pending.append(k)
        elif c.get("id"):
            found[k] = c["id"]
        else:
            none.append(k)
    return {"v": 1, "updated": vandaag.isoformat(), "found": found, "none": none, "pending": pending}


def schrijf(pad, obj):
    pathlib.Path(pad).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")


def run(client, max_min=15, max_verz=1500, droog=False, vandaag=None, klok=time.monotonic, slaap=time.sleep):
    vandaag = vandaag or dt.date.today()
    data = laad(DATA, None)
    if not data:
        print("Spotify: geen site/data.json, overgeslagen")
        return 0
    arts = artiesten(data)
    raw = laad(CACHE, {})
    cache = raw.get("artists", {}) if isinstance(raw, dict) else {}
    cache = {k: c for k, c in cache.items() if isinstance(c, dict)}
    overrides = laad(OVERRIDES, {})
    if not isinstance(overrides, dict):
        overrides = {}
    todo = sorted((k for k in arts if nodig(cache, k, vandaag) and k not in overrides), key=lambda k: (arts[k]["eerste"], k))
    print(f"Spotify: {len(arts)} artiesten met een Spotify-knop, {len(todo)} nog op te zoeken (max {max_verz} verzoeken, {max_min:g} min)")
    if droog:
        return 0
    start, nieuw_gevonden, nieuw_niet, fout = klok(), 0, 0, 0
    if client and todo:
        try:
            for k in todo:
                if klok() - start > max_min * 60 or getattr(client, "verzoeken", 0) >= max_verz:
                    print("Spotify: budget op, de rest volgende keer")
                    break
                try:
                    id_ = zoek_op(client, arts[k]["naam"], slaap)
                except Gestopt:
                    raise
                except (requests.RequestException, ValueError, KeyError) as ex:
                    fout += 1
                    print(f"Spotify: zoeken mislukt voor één artiest ({type(ex).__name__}), later opnieuw")
                    if fout >= 10:
                        print("Spotify: te veel fouten achter elkaar, gestopt")
                        break
                    continue
                fout = 0
                cache[k] = {"id": id_, "t": vandaag.isoformat()}
                nieuw_gevonden += bool(id_)
                nieuw_niet += not id_
                slaap(PAUZE)
        except Gestopt as ex:
            print("Spotify: gestopt:", ex)
    elif todo:
        print("Spotify: geen sleutels ingesteld, niets opgezocht (bekende uitkomsten blijven staan)")
    # oude, nergens meer gebruikte cache-items opruimen
    grens = (vandaag - dt.timedelta(days=BEWAAR_DAGEN)).isoformat()
    cache = {k: c for k, c in cache.items() if k in arts or str((c or {}).get("t", "")) >= grens}
    if cache or OUT.exists() or client:
        schrijf(CACHE, {"v": 1, "artists": cache})
        pub = publiceer(arts, cache, overrides, vandaag)
        schrijf(OUT, pub)
        print(f"Spotify: nieuw {nieuw_gevonden} gevonden, {nieuw_niet} niet gevonden; in de app: {len(pub['found'])} gevonden, "
              f"{len(pub['none'])} grijs, {len(pub['pending'])} nog te zoeken")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--max-minuten", type=float, default=15)
    p.add_argument("--max-verzoeken", type=int, default=2500)
    p.add_argument("--droog", action="store_true")
    a = p.parse_args(argv)
    cid, secret = os.environ.get("SPOTIFY_CLIENT_ID", "").strip(), os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    client = Spotify(cid, secret) if cid and secret else None
    return run(client, a.max_minuten, a.max_verzoeken, a.droog)


if __name__ == "__main__":
    sys.exit(main())
