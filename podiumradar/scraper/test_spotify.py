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
check("'komt op 12 oktober' weg", sp.varianten("Khalid komt op 12 oktober"), ["Khalid komt op 12 oktober", "Khalid"])
check("'op 10 oktober' weg", sp.varianten("Jill Scott op 10 oktober")[-1], "Jill Scott")
check("'op woensdag' blijft (reeksnaam, geen datum)", sp.varianten("Muziek op Woensdag"), ["Muziek op Woensdag"])
check("'solo' weg", sp.varianten("Jason Moran solo")[-1], "Jason Moran")
check("'with Strings' weg", sp.varianten("Starsailor with Strings")[-1], "Starsailor")
check("'luistersessie' weg", sp.varianten("Fontaines D.C. luistersessie")[-1], "Fontaines D.C.")
check("'op' midden in de naam blijft", sp.varianten("Spoor op Zuid"), ["Spoor op Zuid"])
check("'Live' als hele naam blijft", sp.varianten("Live"), ["Live"])
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

def nep_run(client, data, cache=None, overrides=None, overrides_raw=None, **kw):
    """Draait run() met tijdelijke bestanden; geeft (spotify.json, cache) terug."""
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        sp.DATA, sp.CACHE, sp.OVERRIDES, sp.OUT = t / "data.json", t / "cache.json", t / "ov.json", t / "spotify.json"
        sp.DATA.write_text(json.dumps(data))
        if cache is not None: sp.CACHE.write_text(json.dumps({"v": 1, "artists": cache}))
        if overrides is not None: sp.OVERRIDES.write_text(json.dumps(overrides))
        if overrides_raw is not None: sp.OVERRIDES.write_text(overrides_raw)
        nep_run.rc = sp.run(client, vandaag=VANDAAG, slaap=lambda s: None, **kw)
        nep_run.tmp = [x.name for x in t.iterdir() if x.name.endswith(".tmp")]
        pub = json.loads(sp.OUT.read_text()) if sp.OUT.exists() else None
        if pub is not None:   # 'pending' staat niet in het bestand voor de app; hier afgeleid zodat de tests het kunnen controleren
            pub["pending"] = sorted(set(sp.artiesten(data)) - set(pub["found"]) - set(pub["none"]) - set(pub["skip"]))
        return pub, (json.loads(sp.CACHE.read_text())["artists"] if sp.CACHE.exists() else None)

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
for code, js, hdr in [(429, {}, {"Retry-After": "85833"}), (429, {}, {"Retry-After": "901"}), (403, {}, {})]:
    try:
        sp.Spotify("id", "geheim", Sessie([Antw(code, js, hdr)]), slapen.append).zoek("X"); gestopt = False
    except sp.Gestopt:
        gestopt = True
    check(f"{code} {js or hdr}: Gestopt", gestopt, True)
s = Sessie([Antw(429, headers={"Retry-After": "600"}), Antw(200, {"artists": {"items": []}})])
slapen.clear(); c = sp.Spotify("id", "geheim", s, slapen.append)
check("429 tot 15 min: wacht af (bijvoorbeeld net voor een nieuwe dag quotum)", (c.zoek("X"), slapen), ([], [601.0]))
s = Sessie([Antw(503), Antw(200, {"artists": {"items": []}})])
check("5xx: opnieuw", sp.Spotify("id", "geheim", s, lambda x: None).zoek("X"), [])


# ---- voorstelling - artiest, reeksen, voetbal
check("'Voorstelling - Artiest' (klassiek): niet opzoeken", sp.eligible(ev("Grip - Rayen Panday", "Klassiek", "thea1"), V["thea1"]), False)
check("  ...maar wel een knop (zoeklink)", sp.basis(ev("Beethoven - Pavel Haas Quartet", "Klassiek"), V["pop1"]), True)
check("pop 'Band - Zaal' wel opzoeken", sp.eligible(ev("Band X - Live", "Overig"), V["pop1"]), True)
check("reeks (Comedy Tunes) geen artiest", sp.eligible(ev("Comedy Tunes", "Comedy", "thea1"), V["thea1"]), False)
check("cabaretier wel", sp.eligible(ev("Hans Teeuwen", "Cabaret", "thea1"), V["thea1"]), True)
check("voetbal (Ajax - NEC) geen knop", sp.basis(ev("Ajax - N.E.C.", "Overig"), V["pop1"]), False)
check("masterclass geen knop", sp.basis(ev("Masterclass", "Klassiek"), V["pop1"]), False)

# ---- 'Reeks: Artiest': beide kanten, alleen bij precies één treffer
def kant(db): return sp.zoek_op(Nep(db), "Discover: Ronker", lambda x: None)
check("dubbele punt: alleen artiest bestaat", kant({"Ronker": [{"id": ID1, "name": "Ronker"}]}), ID1)
check("dubbele punt: alleen reeks bestaat (bekende naam)", kant({"Discover": [{"id": ID2, "name": "Discover", "popularity": 40}]}), ID2)
check("dubbele punt: allebei bestaan -> grijs", kant({"Ronker": [{"id": ID1, "name": "Ronker"}], "Discover": [{"id": ID2, "name": "Discover", "popularity": 40}]}), None)
nep = Nep({"Discover: Ronker": [{"id": ID3, "name": "Discover: Ronker"}], "Ronker": [{"id": ID1, "name": "Ronker"}]})
check("hele naam wint van de delen", (sp.zoek_op(nep, "Discover: Ronker", lambda x: None), nep.vragen), (ID3, ["Discover: Ronker"]))

# ---- de kant vóór de dubbele punt telt alleen bij een bekende artiest; de kant erna altijd
def kant2(db, naam="Up Close: Ronker"): return sp.zoek_op(Nep(db), naam, lambda x: None)
check("links: kleine artiest telt niet", kant2({"Up Close": [{"id": ID2, "name": "Up Close", "popularity": 3}]}), None)
check("links: bekende artiest telt wel", kant2({"Up Close": [{"id": ID2, "name": "Up Close", "popularity": 60}]}), ID2)
check("rechts: kleine artiest telt wel", kant2({"Ronker": [{"id": ID1, "name": "Ronker", "popularity": 1}]}), ID1)
check("links klein en rechts klein: rechts wint", kant2({"Up Close": [{"id": ID2, "name": "Up Close", "popularity": 3}], "Ronker": [{"id": ID1, "name": "Ronker", "popularity": 2}]}), ID1)
check("kies minpop", (sp.kies("Foo", [{"id": ID1, "name": "Foo", "popularity": 10}], 25), sp.kies("Foo", [{"id": ID1, "name": "Foo", "popularity": 30}], 25)), (None, ID1))

# ---- logregels per artiest
regels = []
sp.zoek_op(Nep({"Ronker": [{"id": ID1, "name": "Ronker", "popularity": 7}]}), "Discover: Ronker", lambda x: None, regels.append)
sp.zoek_op(Nep({"Band Z": [{"id": ID3, "name": "Band Zee", "popularity": 7}]}), "Band Z", lambda x: None, regels.append)
check("logregels", regels, ["  gevonden (deel van naam): Discover: Ronker -> Ronker (populariteit 7)", "  niet gevonden: Band Z (bovenaan bij Spotify: Band Zee)"])

# ---- nieuwe NOT_MUSIC-woorden
check("social dance geen knop", sp.basis(ev("Social Dance: Swing", "Overig"), V["pop1"]), False)
check("spelletjesavond geen knop", sp.basis(ev("Spelletjesavond", "Overig"), V["pop1"]), False)
check("echte band met 'meeting' erin? (woordgrens)", sp.basis(ev("Meetings of Fools", "Overig"), V["pop1"]), True)

# ---- programma-achtige namen worden nooit grijs
D2 = {"venues": V, "events": [ev("Bill Stewart Trio ft. Larry Grenadier", "Overig", id_="s1"), ev("Gewone Band", "Overig", id_="s2")]}
pub, _ = nep_run(Nep(), D2)
check("ft.-naam: zoeklink in plaats van grijs", (sp.key("Bill Stewart Trio ft. Larry Grenadier") in pub["pending"], sp.key("Gewone Band") in pub["none"]), (True, True))

# ---- overrides
pub, _ = nep_run(Nep(), DATA, overrides_raw='{"Band A": " Skip ", "bandb": null,}')
check("ongeldige overrides: niets gepubliceerd, rc 1", (pub, nep_run.rc), (None, 1))
pub, _ = nep_run(Nep(), DATA, overrides_raw='{"Band A": " Skip "}')
check("overrides: leesbare naam en hoofdletters", pub["skip"], [kA])

# ---- atomisch schrijven en corrupte cache
pub, _ = nep_run(Nep(), DATA)
check("geen .tmp-bestand achtergebleven", nep_run.tmp, [])
import io, contextlib
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t); (t / "c.json").write_text('{"v":1,"artists":{"ban')
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): res = sp.laad(t / "c.json", {})
    check("corrupte cache: melding en leeg", (res, "onleesbaar" in buf.getvalue()), ({}, True))

# ---- tijdbudget
class Sessie2(Sessie):
    pass
c = sp.Spotify("id", "geheim", Sessie([Antw(200, {"artists": {"items": []}})]), lambda x: None)
c.deadline = 0.0   # al verstreken
try:
    c.zoek("X"); b = False
except sp.Gestopt:
    b = True
check("deadline verstreken: Gestopt", b, True)
c = sp.Spotify("id", "geheim", Sessie([Antw(429, headers={"Retry-After": "60"})]), lambda x: None)
c.deadline = __import__("time").monotonic() + 10
try:
    c.zoek("X"); b = False
except sp.Gestopt:
    b = True
check("wachten voorbij de deadline: Gestopt", b, True)

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)"))
sys.exit(1 if fouten else 0)
