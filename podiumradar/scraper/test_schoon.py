"""Tests voor scraper/schoon.py (geen internet nodig). Draaien:  python scraper/test_schoon.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import schoon as s

fouten = 0
def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht
    fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))

basis = {"date": "2026-11-01", "time": "20:00", "title": "Band", "url": "https://x.nl/a b", "genre": "Pop", "id": "s123", "v": "paradiso-amsterdam", "first_seen": "2026-10-01"}
def ev(**kw): return s.schoon_event({**basis, **kw})[0]
def reden(**kw): return s.schoon_event({**basis, **kw})[1]

check("gewoon event blijft", ev()["title"], "Band")
check("spatie in url -> %20", ev()["url"], "https://x.nl/a%20b")
check("stuurtekens en dubbele spaties weg", ev(title="Ba\x00nd ‮  X\n")["title"], "Ba nd X")
check("lange titel afgekapt", len(ev(title="x" * 500)["title"]), 200)
check("javascript-link wordt leeg", ev(url="javascript:alert(1)")["url"], "")
check("url met regeleinde wordt leeg", ev(url="https://a.nl/x\r\nEND:VEVENT")["url"], "")
check("onbekend veld weg", "evil" in ev(evil="<script>"), False)
check("slechte datum -> weg", reden(date="2026-13-45"), "datum")
check("datum ver in het verleden -> weg", reden(date="1970-01-01"), "datum")
check("geen titel -> weg", reden(title=None), "titel")
check("titel alleen stuurtekens -> weg", reden(title="\x00\x01"), "titel")
check("id met aanhalingsteken -> weg", reden(id='"><img src=x>'), "id")
check("podium-id met rare tekens -> weg", reden(v="a b"), "podium-id")
check("tijd 25:00 wordt None", ev(time="25:00")["time"], None)
check("tijd als getal wordt None", ev(time=2000)["time"], None)
check("support als tekst wordt genegeerd", "support" in ev(support="abc"), False)
check("support lijst opgeschoond", ev(support=["A", "", None, "B" * 200])["support"], ["A", "B" * 80])
check("prijs 15.5 blijft", ev(price=15.5)["price"], 15.5)
check("prijs negatief weg", "price" in ev(price=-3), False)
check("prijs True weg", "price" in ev(price=True), False)
check("prijs NaN weg", "price" in ev(price=float("nan")), False)
check("einddatum voor begindatum weg", "end" in ev(end="2026-10-01"), False)
check("einddatum blijft", ev(end="2026-12-01")["end"], "2026-12-01")
check("einddatum ver weg (2032) blijft: blijvende tentoonstelling", ev(date="2026-06-27", end="2032-12-31")["end"], "2032-12-31")
check("einddatum absurd ver weg (2200) valt weg, event blijft", ("end" in ev(end="2200-01-01"), ev(end="2200-01-01")["title"]), (False, "Band"))
check("status sold blijft, ander weg", (ev(status="sold").get("status"), "status" in ev(status="<b>")), ("sold", False))
check("times opgeschoond", ev(times=[{"a": "X", "s": "20:30"}, {"a": "Y", "s": "xx"}, 5])["times"], [{"a": "X", "s": "20:30"}])
check("dur buiten bereik weg", "dur" in ev(dur=99999), False)
check("geen object", s.schoon_event("tekst")[1], "geen object")

v = s.schoon_venue({"name": " Paradiso\x00 ", "city": "Amsterdam", "prov": "Noord-Holland", "type": "pop", "lat": 52.3, "lon": 4.9})
check("podium schoon", (v["name"], v["lat"], v["type"]), ("Paradiso", 52.3, "pop"))
check("onbekend podiumtype wordt pop", s.schoon_venue({"name": "X", "type": "<b>"})["type"], "pop")
check("coördinaat buiten bereik wordt None", (s.schoon_venue({"name": "X", "lat": 999, "lon": 4})["lat"]), None)
check("podium zonder naam weg", s.schoon_venue({"name": None}), None)

data = {"updated": "2026-10-09 08:00", "venues": {"paradiso-amsterdam": {"name": "Paradiso", "city": "A", "prov": "", "type": "pop", "lat": 1, "lon": 2}, "ongebruikt": {"name": "Leeg", "city": "B"}},
        "events": [basis, {**basis, "id": "s2", "v": "bestaat-niet"}, {**basis, "id": "s3", "title": None}, "rommel"]}
out, st = s.schoon_alles(data)
check("alles: 1 event over", (len(out["events"]), st["in"], st["weg"]), (1, 4, 3))
check("alles: redenen geteld", dict(st["redenen"]), {"onbekend podium": 1, "titel": 1, "geen object": 1})
check("alles: ongebruikt podium valt weg", list(out["venues"]), ["paradiso-amsterdam"])

# ---- vangnet bij stille uitval van een bron
import datetime as dt
D = dt.date(2026, 10, 9)
st = {}
check("gezonde bron", (s.vangnet(st, "A|pop", 40, 38, D), st["A|pop"]), ("ok", {"ok": "2026-10-09", "n": 38}))
st = {"A|pop": {"ok": "2026-10-08", "n": 40}}
check("plots leeg: oude items aanhouden", s.vangnet(st, "A|pop", 40, 0, D), "houd")
check("... en de laatst gezonde dag blijft staan", st["A|pop"]["ok"], "2026-10-08")
st = {"A|pop": {"ok": "2026-10-01", "n": 40}}
check("7 dagen leeg: loslaten", s.vangnet(st, "A|pop", 40, 0, D), "vervallen")
st = {"A|pop": {"ok": "2026-10-04", "n": 40}}
check("5 dagen leeg: nog aanhouden", s.vangnet(st, "A|pop", 40, 0, D), "houd")
check("kleine bron (3 items) die leeg wordt: geen vangnet", s.vangnet({}, "B|pop", 3, 0, D), "ok")
check("grote bron zakt onder een kwart: aanhouden", s.vangnet({}, "C|pop", 100, 10, D), "houd")
check("grote bron zakt een beetje: gezond", s.vangnet({}, "C|pop", 100, 60, D), "ok")
st = {}
check("eerste keer leeg zonder status: begint nu te tellen", (s.vangnet(st, "D|pop", 20, 0, D), st["D|pop"]["ok"]), ("houd", "2026-10-09"))
check("kapotte status wordt hersteld", s.vangnet({"E|pop": {"ok": "geen datum"}}, "E|pop", 20, 0, D), "houd")

real = pathlib.Path(__file__).resolve().parent.parent / "site/data.json"
if real.exists():
    d = json.loads(real.read_text(encoding="utf-8"))
    out, st = s.schoon_alles(d)
    check("echte data.json: bijna alles blijft (< 0,5% weg)", (st["weg"] / max(1, st["in"]) < 0.005, dict(st["redenen"])), (True, dict(st["redenen"])))
    check("echte data.json: geen verlies aan podia met events", len(out["venues"]) >= len({e["v"] for e in d["events"]}) - 3, True)

print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)"))
sys.exit(1 if fouten else 0)
