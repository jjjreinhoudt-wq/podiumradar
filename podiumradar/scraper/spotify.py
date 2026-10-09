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
  site/spotify.json           {"v":1,"updated":datum,"found":{sleutel: id},"none":[sleutel],"skip":[sleutel]}
                              (alleen artiesten waarbij de app een Spotify-knop toont; wat nog niet is opgezocht staat er
                              niet in en krijgt in de app een gewone zoeklink; 'skip' = handmatig verborgen via de overrides)
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
MAX_WACHT = 900              # langer dan dit (seconden) wachten op Spotify we niet af: stoppen, morgen verder
LINKS_MINPOP = 25            # 'Artiest: Show': de artiest vóór de dubbele punt telt pas bij deze populariteit (voorkomt dat
                             # een reeksnaam als 'Up Close' of 'Next Stage' een toevallige kleine artiest oplevert)

# Zelfde indeling als app.js (type per item), zodat de app en dit script het eens zijn over wat een artiest is
THEATER_GENRES = {"Cabaret", "Comedy", "Musical", "Toneel", "Dans", "Opera", "Theater", "Jeugd"}
TYPE_OF = {"thea": "thea", "film": "film", "museum": "expo", "festival": "fest"}
ARTIEST_GENRES = {"Cabaret", "Comedy"}   # de titel is de naam van de cabaretier of comedian
GEEN_MUZIEK = {"Feest", "Lezing"}
NOT_MUSIC = re.compile(r"workshop|lezing|cursus|quiz|bingo|borrel|lunch|diner|rondleiding|open dag|proefles|clinic|"
                       r"filmavond|tentoonstelling|expositie|vergadering|netwerk|markt|\wbeurs\b|yoga|game night|jam ?sessi(e|on)|"
                       r"open (mic|podium|stage)|proeverij|proefavond|springkussen|boekenclub|(hedon|nacht) academy|"
                       r"publieke tribune|masterclass|^(ajax|vitesse)\s+-\s|"
                       r"social dance|spelletjes|vaccinatie|science caf|subsidie|boekpresentatie|podcast|business club|\bmeeting\b|"
                       r"protestborden|woonprotest|stadssafari|crafternoon|design week|\bddw\b|cultuurnacht|museumnacht", re.I)
# Reeksen en avonden in plaats van een artiest (alleen getoetst op cabaret/comedy-namen)
SERIE = re.compile(r"comedy|cabaret|stand-?up|try-?out|conferen|caf[eé]\b|\bclub\b|night|train\b|kwis", re.I)
# 'Voorstelling - Artiest': bij deze genres is het deel voor het streepje meestal de voorstelling, niet de artiest
SHOW_EERST = {"Klassiek", "Cabaret", "Comedy", "Tribute"}
# Namen die geen enkele artiest zijn (ft./presents/komma's of heel lang): nooit grijs, maar een gewone zoeklink
PROGRAMMA = re.compile(r"\s(ft\.?|feat\.?|featuring|presents?|met|with|spelen?|speelt|plays?)\s|,", re.I)


class Gestopt(Exception):
    """Spotify laat niet meer toe (quotum, Premium verlopen, geen toegang): stoppen, bekende uitkomsten blijven."""


def event_type(e, v):
    g, vt = e.get("genre"), (v or {}).get("type")
    if g == "Film" and vt != "festival":
        return "film"
    if g == "Tentoonstelling" and vt != "festival":
        return "expo"
    return TYPE_OF.get(vt) or ("thea" if g in THEATER_GENRES else "pop")


def dash_show(e):
    """Titel 'Voorstelling - Artiest' bij een genre waar het eerste deel meestal de voorstelling is."""
    titel = re.sub(r"\s*\((festival|festival, dag \d)\)$", "", e.get("title", ""), flags=re.I)
    return " - " in titel and e.get("genre") in SHOW_EERST


def basis(e, v):
    """Hoort er bij dit item uberhaupt een Spotify-knop (opzoeken of alleen een zoeklink)?"""
    if str(e.get("id", ""))[:1] == "f":      # festivalitems: de naam is het festival
        return False
    t, g = event_type(e, v), e.get("genre")
    if t in ("film", "expo", "fest") or NOT_MUSIC.search(e.get("title", "")):
        return False
    return g in ARTIEST_GENRES or (t == "pop" and g not in GEEN_MUZIEK)


def eligible(e, v):
    """Wordt de artiest van dit item op Spotify opgezocht? (zelfde regels als spotState in app.js)"""
    if not basis(e, v) or dash_show(e):
        return False
    if e.get("genre") in ARTIEST_GENRES:
        namen = acts(e)
        return not (namen and SERIE.search(namen[0]))
    return True


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


MAANDEN = "jan(?:uari)?|feb(?:ruari)?|maart|mrt|apr(?:il)?|mei|juni?|juli?|aug(?:ustus)?|sep(?:t(?:ember)?)?|okt(?:ober)?|nov(?:ember)?|dec(?:ember)?"
# Achter de artiestnaam in titels: 'Khalid komt op 12 oktober', 'Jason Moran solo', 'Starsailor with Strings'
RUIS_ACHTER = re.compile(
    r"\s+(?:(?:komt\s+)?op\s+\d{1,2}\s+(?:" + MAANDEN + r")\.?(?:\s+\d{4})?"
    r"|solo|live|in concert|unplugged|acoustic|akoestisch|with strings|with orchestra|luistersessie|listening session)\s*$", re.I)


def varianten(naam):
    """Zoeknamen, van volledig naar vooral de artiest zelf:
    de hele naam; zonder (NL)/(18+) achteraan; het deel voor ' ✦ ', ' • ', ' | ' of ' / '; zonder 'komt op 12 oktober',
    'solo', 'with strings' e.d. achteraan; bij 'Reeks: Artiest' of 'Artiest: Show' het deel voor en het deel na de dubbele punt.
    Nooit gesplitst op '&' of ',': dat zijn vaak duo's of groepsnamen. Alleen een exacte treffer telt toch."""
    n = naam.strip()
    zonder = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    eerste = SCHEIDERS.split(zonder)[0].strip()
    schoon = RUIS_ACHTER.sub("", eerste).strip()
    kandidaten = [(n, 3), (zonder, 3), (eerste, 4), (schoon, 4)]
    if ":" in schoon:
        voor, na = schoon.split(":", 1)
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


def kies_kandidaat(naam, kandidaten, minpop=0):
    """Beste exacte treffer (populairste, minstens minpop), of None."""
    goed = [c for c in kandidaten if c and ID_RE.match(str(c.get("id", ""))) and zelfde_naam(naam, c.get("name", ""))
            and (c.get("popularity") or 0) >= minpop]
    return max(goed, key=lambda c: c.get("popularity") or 0) if goed else None


def kies(naam, kandidaten, minpop=0):
    """Id van de beste exacte treffer (populairste), of None."""
    c = kies_kandidaat(naam, kandidaten, minpop)
    return c["id"] if c else None


class Spotify:
    """Dunne laag om de Spotify Web API (client credentials). Geheimen worden nooit geprint."""

    def __init__(self, cid, secret, sessie=None, slaap=time.sleep):
        self.cid, self.secret = cid, secret
        self.s = sessie or requests.Session()
        self.slaap = slaap
        self.tok = None
        self.verzoeken = 0
        self.deadline = None     # tijdstip (time.monotonic) waarna er niets meer wordt verstuurd of afgewacht

    def _token(self):
        r = self.s.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=(self.cid, self.secret), timeout=30)
        if r.status_code in (400, 401):
            raise Gestopt("Spotify weigert de sleutels (controleer SPOTIFY_CLIENT_ID en SPOTIFY_CLIENT_SECRET)")
        r.raise_for_status()
        self.tok = r.json()["access_token"]

    def zoek(self, naam):
        """Lijst artiesten [{'id','name','popularity'}] bij deze naam."""
        for poging in range(5):
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise Gestopt("tijdbudget op: de rest volgende keer")
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
                if wacht > MAX_WACHT:        # in de praktijk een dagquotum (Retry-After ~24 uur): morgen verder
                    raise Gestopt(f"Spotify-quotum bereikt (wacht {int(wacht)} s): morgen verder")
                if self.deadline is not None and time.monotonic() + wacht + 1 > self.deadline:
                    raise Gestopt("tijdbudget op tijdens het wachten op Spotify: de rest volgende keer")
                self.slaap(wacht + 1)
                continue
            if r.status_code >= 500:
                self.slaap(2 ** poging)
                continue
            r.raise_for_status()
            return (r.json().get("artists") or {}).get("items") or []
        raise requests.RequestException("Spotify gaf na meerdere pogingen geen antwoord")


def waarschuw(tekst):
    """Melding die in GitHub Actions op de samenvatting van de run staat, ook als de run groen blijft."""
    print(f"::warning title=Spotify::{tekst}" if os.environ.get("GITHUB_ACTIONS") else "Spotify: " + tekst)


def laad(pad, standaard):
    p = pathlib.Path(pad)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return standaard
    except (OSError, ValueError) as ex:
        waarschuw(f"{p.name} is onleesbaar ({type(ex).__name__}) en wordt als leeg behandeld")
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


def colon_delen(naam):
    """Beide kanten van 'Reeks: Artiest' / 'Artiest: Show'."""
    zonder = re.sub(r"\s*\([^)]*\)\s*$", "", naam.strip()).strip()
    eerste = SCHEIDERS.split(zonder)[0].strip()
    if ":" not in eerste:
        return []
    voor, na = eerste.split(":", 1)
    return [x for x in (voor.strip(), na.strip()) if len(key(x)) >= 4]


def zoek_op(client, naam, slaap=time.sleep, log=lambda t: None):
    """Id van de artiest op Spotify, of None. Eerst de hele naam en de varianten zonder dubbele punt; pas als die niets
    opleveren beide kanten van 'Reeks: Artiest': dan telt alleen een treffer als precies een van de twee een artiest is
    (anders is het onduidelijk of de reeks of de artiest bedoeld wordt: liever grijs). Het deel vóór de dubbele punt
    moet bovendien bekend genoeg zijn (LINKS_MINPOP). `log` krijgt per artiest één regel voor het logboek."""
    delen = colon_delen(naam)
    eerst = [v for v in varianten(naam) if v not in delen]
    pauze = False
    top = ""
    for v in eerst:
        if pauze:
            slaap(PAUZE)
        pauze = True
        lijst = client.zoek(v)
        c = kies_kandidaat(v, lijst)
        if c:
            log(f"  gevonden: {naam} -> {c.get('name')} (populariteit {c.get('popularity')}, gezocht op '{v}')")
            return c["id"]
        top = ", ".join(str(x.get("name")) for x in lijst[:3])
    treffers = []
    for i, v in enumerate(delen):
        if pauze:
            slaap(PAUZE)
        pauze = True
        lijst = client.zoek(v)
        c = kies_kandidaat(v, lijst, LINKS_MINPOP if i == 0 and len(delen) == 2 else 0)
        if c:
            treffers.append(c)
        top = ", ".join(str(x.get("name")) for x in lijst[:3]) or top
    if len(treffers) == 1:
        c = treffers[0]
        log(f"  gevonden (deel van naam): {naam} -> {c.get('name')} (populariteit {c.get('popularity')})")
        return c["id"]
    log(f"  niet gevonden: {naam}" + (" (twee delen zijn allebei een artiest)" if treffers else f" (bovenaan bij Spotify: {top or 'niets'})"))
    return None


def publiceer(arts, cache, overrides, vandaag):
    """Maakt de inhoud van site/spotify.json."""
    found, none, pending, skip = {}, [], [], []
    for k in sorted(arts):
        o = overrides.get(k, "geen") if isinstance(overrides, dict) else "geen"
        if o == "skip":
            skip.append(k)
            continue
        if o != "geen":                           # id of null uit de overrides
            if o and ID_RE.match(str(o)):
                found[k] = o
            else:
                none.append(k)
            continue
        c = cache.get(k)
        naam = arts[k]["naam"]
        if not c:
            pending.append(k)
        elif c.get("id"):
            found[k] = c["id"]
        elif len(naam) > 40 or PROGRAMMA.search(naam):
            pending.append(k)      # geen artiestnaam (programma, gasten, lang): een gewone zoeklink is beter dan grijs
        else:
            none.append(k)
    return {"v": 1, "updated": vandaag.isoformat(), "found": found, "none": none, "pending": pending, "skip": skip}


def schrijf(pad, obj):
    """Atomisch: eerst een tijdelijk bestand, dan vervangen. Een onderbroken run laat nooit een halve cache achter."""
    p = pathlib.Path(pad)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def run(client, max_min=15, max_verz=1500, droog=False, vandaag=None, klok=time.monotonic, slaap=time.sleep, log=lambda t: None):
    vandaag = vandaag or dt.date.today()
    data = laad(DATA, None)
    if not data:
        print("Spotify: geen site/data.json, overgeslagen")
        return 0
    arts = artiesten(data)
    raw = laad(CACHE, {})
    cache = raw.get("artists", {}) if isinstance(raw, dict) else {}
    cache = {k: c for k, c in cache.items() if isinstance(c, dict)}
    overrides = laad(OVERRIDES, None) if OVERRIDES.exists() else {}
    if not isinstance(overrides, dict):
        print("::error::spotify_overrides.json is geen geldig JSON-woordenboek (komma te veel?): niets gepubliceerd, "
              "de vorige spotify.json blijft staan" if os.environ.get("GITHUB_ACTIONS") else "Spotify: spotify_overrides.json is ongeldig, gestopt")
        return 1
    # "Skip", " skip" of de leesbare naam ("Ajax") werken ook; onbekende sleutels en ongeldige ids worden gemeld
    overrides = {key(k): (v.strip().lower() if isinstance(v, str) and v.strip().lower() == "skip" else v) for k, v in overrides.items()}
    for k, v in overrides.items():
        if k not in arts:
            waarschuw(f"spotify_overrides.json: '{k}' komt bij geen artiest voor")
        if v not in (None, "skip") and not ID_RE.match(str(v)):
            waarschuw(f"spotify_overrides.json: '{k}' heeft geen geldig Spotify-id (22 tekens) en wordt grijs")
    todo = sorted((k for k in arts if nodig(cache, k, vandaag) and k not in overrides), key=lambda k: (arts[k]["eerste"], k))
    print(f"Spotify: {len(arts)} artiesten met een Spotify-knop, {len(todo)} nog op te zoeken (max {max_verz} verzoeken, {max_min:g} min)")
    if droog:
        return 0
    start, nieuw_gevonden, nieuw_niet, fout = klok(), 0, 0, 0
    if client is not None and hasattr(client, "deadline"):
        client.deadline = time.monotonic() + (max_min + 2) * 60     # ook een lang wachten op Spotify houdt de run binnen het budget
    if client and todo:
        try:
            for k in todo:
                if klok() - start > max_min * 60 or getattr(client, "verzoeken", 0) >= max_verz:
                    print("Spotify: budget op, de rest volgende keer")
                    break
                try:
                    id_ = zoek_op(client, arts[k]["naam"], slaap, log)
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
            waarschuw(f"gestopt: {ex}")
    elif todo:
        waarschuw("geen sleutels ingesteld (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET), niets opgezocht; bekende uitkomsten blijven staan")
    # oude, nergens meer gebruikte cache-items opruimen
    grens = (vandaag - dt.timedelta(days=BEWAAR_DAGEN)).isoformat()
    cache = {k: c for k, c in cache.items() if k in arts or str((c or {}).get("t", "")) >= grens}
    if cache or OUT.exists() or client:
        schrijf(CACHE, {"v": 1, "artists": cache})
        pub = publiceer(arts, cache, overrides, vandaag)
        schrijf(OUT, {k: v for k, v in pub.items() if k != "pending"})   # 'pending' is alleen voor het logboek: de app heeft het niet nodig
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
    return run(client, a.max_minuten, a.max_verzoeken, a.droog, log=lambda t: print(t, flush=True))


if __name__ == "__main__":
    sys.exit(main())
