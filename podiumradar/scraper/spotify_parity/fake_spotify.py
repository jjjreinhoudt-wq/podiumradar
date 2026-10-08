"""Maakt in een KOPIE van de site een nep-spotify.json (en expect.json met wat de app per event moet tonen).

Hoort bij spotify_parity/parity.js: controleert dat app.js (spotState) en spotify.py (basis/eligible) dezelfde events een
Spotify-knop geven. Gebruik:
  cp -r site /tmp/sitecopy && python scraper/spotify_parity/fake_spotify.py /tmp/sitecopy
  python -m http.server 8771 -d /tmp/sitecopy &
  PWPATH=$(npm root -g)/playwright node scraper/spotify_parity/parity.js http://localhost:8771/ /tmp/sitecopy/expect.json
Verwacht: mismatches: 0
"""
import hashlib, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import spotify as sp
SITE = pathlib.Path(sys.argv[1])
data = json.load(open(SITE / 'data.json'))
arts = sp.artiesten(data)
found, none, pending = {}, [], []
for k in sorted(arts):
    h = int(hashlib.md5(k.encode()).hexdigest(), 16) % 10
    if h < 5: found[k] = (hashlib.md5(k.encode()).hexdigest() + "ABCDEFGHIJ")[:22]
    elif h < 8: none.append(k)
    else: pending.append(k)
json.dump({"v": 1, "updated": "2026-10-09", "found": found, "none": none, "pending": pending}, open(SITE / 'spotify.json', 'w'))
ns, ps = set(none), set(pending)
exp = {}
for e in data['events']:
    v = data['venues'].get(e['v'])
    if not sp.eligible(e, v): st = 'search' if (sp.basis(e, v) and sp.dash_show(e)) else 'skip'
    else:
        k = sp.key(sp.acts(e)[0])
        st = ('link:' + found[k]) if k in found else 'none' if k in ns else 'search'   # niet in het bestand: gewone zoeklink
    exp[e['id']] = {"spot": st, "film": sp.event_type(e, v) == "film"}
json.dump(exp, open(SITE / 'expect.json', 'w'))
print(len(found), len(none), len(pending), "artiesten;", sum(1 for x in exp.values() if x['spot'] == 'skip'), "events zonder knop")
