"""Tests voor scraper/spotify.py (Spotify-opzoeken). Draaien:  python scraper/test_spotify.py   (geen internet nodig)"""
import datetime as dt, json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import requests
import spotify as sp

fouten = 0


def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht
    fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))


ID1, ID2, ID3 = "1" * 22, "2" * 22, "3" * 22
VANDAAG = dt.date(2026, 10, 9)

# ---- namen en keuzes
check("varianten reeks: artiest", sp.varianten("Techno Tuesday: Dexon"), ["Techno Tuesday: Dexon", "Techno Tuesday", "Dexon"])
check("varianten datum/zaal weg", sp.varianten("Stereo MC's ✦ vr 7 mei ✦ Luxor Live")[-1], "Stereo MC's")
check("varianten (18+) weg", sp.varianten("Hans Teeuwen (18+)"), ["Hans Teeuwen (18+)", "Hans Teeuwen"])
check("geen splitsing op &", sp.varianten("Simon & Garfunkel"), ["Simon & Garfunkel"])
check("te korte naam", sp.varianten("AB"), [])
check("& = and", sp.zelfde_naam("Simon & Garfunkel", "Simon and Garfunkel"), True)
check("The vooraan", sp.zelfde_naam("The Amity Affliction", "Amity Affliction"), True)
check("accenten", sp.zelfde_naam("Beyoncé", "BEYONCE"), True)
check("geen deelovereenkomst", sp.zelfde_naam("Digger", "Digger Jr"), False)
check("kies populairste exacte", sp.kies("Foo", [{"id": ID1, "name": "Foo", "popularity": 10}, {"id": ID2, "name": "FOO", "popularity": 40}, {"id": ID3, "name": "Foo Fighters", "popularity": 99}]), ID2)
check("kies niets bij andere naam", sp.kies("Foo", [{"id": ID3, "name": "Foo Fighters"}]), None)
check("kies negeert ongeldig id", sp.kies("Foo", [{"id": "kort", "name": "Foo"}]), None)
check("kies zonder popularity", sp.kies("Foo", [{"id": ID1, "name": "Foo"}]), ID1)

# ---- welke items krijgen een Spotify-knop
V = {"pop1": {"type": "pop"}, "thea1": {"type": "thea"}, "film1": {"type": "film"}, "fest1": {"type": "festival"}, "museum1": {"type": "museum"}}
def ev(titel, genre, v="pop1", id_="s1"): return {"title": titel, "genre": genre, "v": v, "id": id_, "date": "2026-11-01"}
check("concert", sp.eligible(ev("Band", "Overig"), V["pop1"]), True)
check("cabaret in theater", sp.eligible(ev("Hans Teeuwen", "Cabaret", "thea1"), V["thea1"]), True)
check("musical", sp.eligible(ev("Cats", "Musical", "thea1"), V["thea1"]), False)
check("toneel in theater", sp.eligible(ev("Hamlet", "Toneel", "thea1"), V["thea1"]), False)
check("film", sp.eligible(ev("Film", "Film", "film1"), V["film1"]), False)
check("expo", sp.eligible(ev("Expo", "Tentoonstelling", "pop1"), V["pop1"]), False)
check("festivalitem (id f..)", sp.eligible(ev("Fest", "Festival", "fest1", "f12"), V["fest1"]), False)
check("workshop", sp.eligible(ev("Workshop Event organisatie", "Overig"), V["pop1"]), False)
check("feest", sp.eligible(ev("Party", "Feest"), V["pop1"]), False)

# ---- nep-Spotify
class Nep:
    def __init__(self, db=None, fout=None):
        self.db, self.fout, self.vragen, self.verzoeken = db or {}, fout, [], 0
    def zoek(self, naam):
        self.verzoeken += 1; self.vragen.append(naam)
        if self.fout: raise self.fout
        return self.db.get(naam, [])

def nep_run(client, data, cache=None, overrides=None, **kw):
    """Draait run() met tijdelijke bestanden; geeft (spotify.json, cache) terug."""
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        sp.DATA, sp.CACHE, sp.OVERRIDES, sp.OUT = t / "data.json", t / "cache.json", t / "ov.json", t / "spotify.json"
        sp.DATA.write_text(json.dumps(data))
        if cache is not None: sp.CACHE.write_text(json.dumps({"v": 1, "artists": cache}))
        if overrides is not None: sp.OVERRIDES.write_text(json.dumps(overrides))
        sp.run(client, vandaag=VANDAAG, slaap=lambda s: None, **kw)
        return (json.loads(sp.OUT.read_text()) if sp.OUT.exists() else None), (json.loads(sp.CACHE.read_text())["artists"] if sp.CACHE.exists() else None)

DATA = {"venues": V, "events": [ev("Band A", "Overig", id_="s1"), ev("Band B", "Overig", id_="s2"), ev("Band C", "Overig", id_="s3"), ev("Hamlet", "Toneel", "thea1", "s4")]}
kA, kB, kC = sp.key("Band A"), sp.key("Band B"), sp.key("Band C")

# ---- hele run
nep = Nep({"Band A": [{"id": ID1, "name": "Band A", "popularity": 5}], "Band B": [{"id": ID3, "name": "Band Bee"}]})
pub, cache = nep_run(nep, DATA)
check("gevonden", pub["found"], {kA: ID1})
check("niet gevonden", sorted(pub["none"]), sorted([kB, kC]))
check("toneel niet in de app-lijst", sp.key("Hamlet") in pub["found"] or sp.key("Hamlet") in pub["none"] or sp.key("Hamlet") in pub["pending"], False)
check("cache bevat alleen id en datum", cache[kA], {"id": ID1, "t": "2026-10-09"})

# ---- cache werkt: niets opnieuw opgezocht
nep = Nep()
pub, _ = nep_run(nep, DATA, cache={kA: {"id": ID1, "t": "2026-01-01"}, kB: {"id": None, "t": "2026-10-01"}, kC: {"id": None, "t": "2026-08-01"}})
check("alleen verouderd 'niet gevonden' opnieuw", nep.vragen, ["Band C"])
check("bekende uitkomsten blijven", pub["found"], {kA: ID1})

# ---- budget en volgorde
nep = Nep()
pub, _ = nep_run(nep, DATA, max_verz=1)
check("max verzoeken: één artiest", len(nep.vragen), 1)
check("rest staat op pending", len(pub["pending"]), 2)

# ---- gestopt (quotum/Premium): bekende blijven, rest pending, geen crash
class Stop(Nep):
    def zoek(self, naam): raise sp.Gestopt("test")
pub, _ = nep_run(Stop(), DATA, cache={kA: {"id": ID1, "t": "2026-10-01"}})
check("gestopt: bekende blijft", pub["found"], {kA: ID1})
check("gestopt: rest pending", sorted(pub["pending"]), sorted([kB, kC]))

# ---- netwerkfouten
nep = Nep(fout=requests.ConnectionError("x"))
pub, _ = nep_run(nep, DATA)
check("netwerkfout: alles pending", len(pub["pending"]), 3)

# ---- zonder sleutels
pub, cache = nep_run(None, DATA)
check("zonder sleutels en zonder cache: niets geschreven", (pub, cache), (None, None))
pub, _ = nep_run(None, DATA, cache={kA: {"id": ID1, "t": "2026-10-01"}})
check("zonder sleutels maar met cache: blijft staan", (pub["found"], len(pub["pending"])), ({kA: ID1}, 2))

# ---- overrides
pub, _ = nep_run(Nep(), DATA, overrides={kA: ID2, kB: None, kC: "skip"})
check("override id", pub["found"], {kA: ID2})
check("override grijs", pub["none"], [kB])
check("override skip", (kC in pub["found"] or kC in pub["none"] or kC in pub["pending"], pub["skip"]), (False, [kC]))

# ---- opruimen
pub, cache = nep_run(Nep(), DATA, cache={"oudeartiest": {"id": ID1, "t": "2024-01-01"}, "recent": {"id": None, "t": "2026-09-01"}})
check("oude cache opgeruimd, recente blijft", sorted(k for k in cache if k in ("oudeartiest", "recent")), ["recent"])

# ---- de HTTP-laag
class Antw:
    def __init__(self, code, js=None, headers=None): self.status_code, self._js, self.headers = code, js or {}, headers or {}
    def json(self): return self._js
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(str(self.status_code))
class Sessie:
    def __init__(self, antwoorden): self.a, self.posts, self.gets = list(antwoorden), 0, []
    def post(self, url, **kw): self.posts += 1; return Antw(200, {"access_token": "T"})
    def get(self, url, **kw): self.gets.append(kw["headers"]["Authorization"]); return self.a.pop(0)
slapen = []
s = Sessie([Antw(401), Antw(200, {"artists": {"items": [{"id": ID1, "name": "X"}]}})])
c = sp.Spotify("id", "geheim", s, slapen.append)
check("401: nieuw token en opnieuw", [x["id"] for x in c.zoek("X")], [ID1])
check("401: twee tokens opgehaald", s.posts, 2)
s = Sessie([Antw(429, headers={"Retry-After": "3"}), Antw(200, {"artists": {"items": []}})])
slapen.clear(); c = sp.Spotify("id", "geheim", s, slapen.append)
check("429 kort: wacht en probeert opnieuw", (c.zoek("X"), slapen), ([], [4.0]))
for code, js, hdr in [(429, {"reason": "QUOTA_EXCEEDED"}, {"Retry-After": "5"}), (429, {}, {"Retry-After": "7200"}), (403, {}, {})]:
    try:
        sp.Spotify("id", "geheim", Sessie([Antw(code, js, hdr)]), slapen.append).zoek("X"); gestopt = False
    except sp.Gestopt:
        gestopt = True
    check(f"{code} {js or hdr}: Gestopt", gestopt, True)
s = Sessie([Antw(503), Antw(200, {"artists": {"items": []}})])
check("5xx: opnieuw", sp.Spotify("id", "geheim", s, lambda x: None).zoek("X"), [])

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)"))
sys.exit(1 if fouten else 0)
