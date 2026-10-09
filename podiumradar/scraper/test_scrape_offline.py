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

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)")); sys.exit(1 if fouten else 0)
